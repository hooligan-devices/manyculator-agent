from google.adk.cli.service_registry import get_service_registry
from app.services.firestore_session import FirestoreSessionService
import logging

logger = logging.getLogger(__name__)

def firestore_session_factory(uri: str, **kwargs):
    logger.info(f"Initializing custom FirestoreSessionService for URI: {uri}")
    return FirestoreSessionService(**kwargs)

# Register the custom scheme 'firestore'
get_service_registry().register_session_service("firestore", firestore_session_factory)
logger.info("Registered custom ADK session service: firestore://")
