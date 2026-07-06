import logging
import json
from typing import Any, Optional

from google.adk.platform import time as platform_time
from google.adk.platform import uuid as platform_uuid
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session
from google.adk.events.event import Event
from google.cloud import firestore

logger = logging.getLogger(__name__)

CHUNK_SIZE = 900_000  # 900KB, well under the 1MB Firestore limit

class FirestoreSessionService(BaseSessionService):
    """Firestore-backed session service for ADK."""

    def __init__(self, **kwargs):
        super().__init__()
        try:
            # Initialize Firestore client pointing to the existing 'calculators' database
            self.db = firestore.Client(database="calculators")
            self.collection = self.db.collection("sessions")
            logger.info("Initialized FirestoreSessionService")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore client for sessions: {e}")
            self.db = None
            self.collection = None

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        session_id = session_id.strip() if session_id and session_id.strip() else platform_uuid.new_uuid()
        
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=state or {},
            last_update_time=platform_time.get_time(),
        )

        if self.collection:
            doc_data = {
                "app_name": session.app_name,
                "user_id": session.user_id,
                "last_update_time": session.last_update_time,
                "state_json": json.dumps(session.state),
            }
            self.collection.document(session_id).set(doc_data)
            logger.debug(f"Created session {session_id} in Firestore")
        
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        if not self.collection:
            return None
            
        doc_ref = self.collection.document(session_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
            
        data = doc.to_dict()
        if data.get("app_name") != app_name or data.get("user_id") != user_id:
            return None
            
        # Fallback for old sessions that used session_data string
        if "session_data" in data:
            try:
                session = Session.model_validate_json(data["session_data"])
            except Exception as e:
                logger.error(f"Failed to parse legacy session_data for {session_id}: {e}")
                return None
        else:
            state = {}
            if "state_json" in data:
                state = json.loads(data["state_json"])
            elif "state" in data:
                # older unpacked legacy
                state = data["state"]
                
            session = Session(
                id=session_id,
                app_name=data.get("app_name", app_name),
                user_id=data.get("user_id", user_id),
                last_update_time=data.get("last_update_time", 0.0),
                state=state,
            )
            
            # Query events subcollection
            events_ref = doc_ref.collection("events")
            query = events_ref.order_by("timestamp", direction=firestore.Query.DESCENDING)
            
            if config:
                if config.after_timestamp is not None:
                    query = query.where(filter=firestore.FieldFilter("timestamp", ">", config.after_timestamp))
                if config.num_recent_events is not None:
                    if config.num_recent_events == 0:
                        query = query.limit(0)
                    else:
                        query = query.limit(config.num_recent_events)
                        
            events = []
            for event_doc in query.stream():
                event_data = event_doc.to_dict()
                if "event_json" in event_data:
                    events.append(Event.model_validate_json(event_data["event_json"]))
                elif "num_chunks" in event_data:
                    # Reconstruct chunked event
                    num_chunks = event_data["num_chunks"]
                    chunks_stream = event_doc.reference.collection("chunks").stream()
                    chunks_dict = {int(c.id): c.to_dict()["data"] for c in chunks_stream}
                    event_json = "".join(chunks_dict[i] for i in range(num_chunks))
                    events.append(Event.model_validate_json(event_json))
            
            # We queried descending to get the N most recent, so reverse it back to chronological
            session.events = list(reversed(events))
                    
        # Apply memory-side filtering for legacy sessions that already have all events loaded
        if "session_data" in data and config:
            if config.num_recent_events is not None:
                if config.num_recent_events == 0:
                    session.events = []
                else:
                    session.events = session.events[-config.num_recent_events:]
            if config.after_timestamp is not None:
                i = len(session.events) - 1
                while i >= 0:
                    if session.events[i].timestamp < config.after_timestamp:
                        break
                    i -= 1
                if i >= 0:
                    session.events = session.events[i + 1:]
                    
        return session

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        if not self.collection:
            return ListSessionsResponse(sessions=[])
            
        query = self.collection.where(filter=firestore.FieldFilter("app_name", "==", app_name))
        if user_id:
            query = query.where(filter=firestore.FieldFilter("user_id", "==", user_id))
            
        sessions = []
        for doc in query.stream():
            data = doc.to_dict()
            try:
                if "session_data" in data:
                    session = Session.model_validate_json(data["session_data"])
                    session.events = []
                else:
                    state = {}
                    if "state_json" in data:
                        state = json.loads(data["state_json"])
                    elif "state" in data:
                        state = data["state"]
                    session = Session(
                        id=doc.id,
                        app_name=data.get("app_name", app_name),
                        user_id=data.get("user_id", ""),
                        last_update_time=data.get("last_update_time", 0.0),
                        state=state,
                        events=[]
                    )
                sessions.append(session)
            except Exception as e:
                logger.warning(f"Skipping invalid session document {doc.id}: {e}")
                
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        if not self.collection:
            return
            
        doc_ref = self.collection.document(session_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("app_name") == app_name and data.get("user_id") == user_id:
                # Firestore shallow delete won't delete subcollections. 
                # This doesn't strictly clean up everything, but it's okay for now.
                doc_ref.delete()
                logger.debug(f"Deleted session {session_id} from Firestore")

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event
            
        updated_event = await super().append_event(session, event)
        session.last_update_time = event.timestamp
        
        if self.collection:
            doc_ref = self.collection.document(session.id)
            
            # Since batches have a limit of 500 writes, and chunks usually aren't that many, 
            # we can batch the update to session and the event creation.
            batch = self.db.batch()
            
            batch.set(doc_ref, {
                "app_name": session.app_name,
                "user_id": session.user_id,
                "last_update_time": session.last_update_time,
                "state_json": json.dumps(session.state)
            }, merge=True)
            
            event_ref = doc_ref.collection("events").document(event.id)
            event_json = event.model_dump_json()
            
            if len(event_json) < CHUNK_SIZE:
                batch.set(event_ref, {
                    "timestamp": event.timestamp,
                    "event_json": event_json
                })
            else:
                chunks = [event_json[i:i+CHUNK_SIZE] for i in range(0, len(event_json), CHUNK_SIZE)]
                batch.set(event_ref, {
                    "timestamp": event.timestamp,
                    "num_chunks": len(chunks)
                })
                for i, chunk in enumerate(chunks):
                    chunk_ref = event_ref.collection("chunks").document(str(i))
                    batch.set(chunk_ref, {"data": chunk})
            
            batch.commit()
            
        return updated_event
