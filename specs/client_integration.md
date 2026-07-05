# Client Integration Guide

This guide details how a frontend client or consumer application should interact with the `manyculator-agent` API.

### Step 1: Establish a Session
Before running the calculator generator, the consumer app must create a user session to track context.
*   **Endpoint**: `POST /apps/app/users/{user_id}/sessions`
*   **Path Parameters**:
    *   `user_id` (string): Unique identifier for the user (e.g. `user_98765`).
*   **Headers**: `Content-Type: application/json`
*   **Request Body**:
    ```json
    {
      "state": {
        "preferred_language": "English",
        "visit_count": 1
      }
    }
    ```
*   **Response (HTTP 200 OK)**:
    ```json
    {
      "id": "e8d75cf8-51f6-49a0-a7d0-1b772951f28b",
      "state": {
        "preferred_language": "English",
        "visit_count": 1
      },
      "created_at": "2026-07-01T20:15:00Z",
      "updated_at": "2026-07-01T20:15:00Z"
    }
    ```
    > [!IMPORTANT]
    > Save the returned `id` (this is your `session_id`). It is required for all messaging and generation endpoints.

---

### Step 2: Call the Agent (Calculator Generation Stream)
Trigger the calculator generation graph by posting a message. This returns a Server-Sent Events (SSE) stream.
*   **Endpoint**: `POST /run_sse` (or `POST /apps/app/users/{user_id}/sessions/{session_id}/messages`)
*   **Headers**: `Content-Type: application/json`
*   **Request Body**:
    ```json
    {
      "app_name": "app",
      "user_id": "user_98765",
      "session_id": "e8d75cf8-51f6-49a0-a7d0-1b772951f28b",
      "new_message": {
        "role": "user",
        "parts": [{"text": "Create a BMI calculator"}]
      },
      "streaming": true
    }
    ```

#### Interpreting the SSE Stream Outcomes
The client receives a stream of JSON chunks formatted as `data: {JSON_PAYLOAD}\n\n`. The final event indicates success or failure.

#### A. Success Event Format
On successful generation, the last events in the stream will contain the final agent response, providing the generated `calculator_id` and the renderable `a2ui_schema`:
```json
{
  "content": {
    "role": "model",
    "parts": [{
      "text": "Your BMI calculator has been generated successfully."
    }]
  },
  "output": {
    "calculator_id": "7129c944-3326-454c-acb3-de1deb745647",
    "a2ui_schema": [
      {
        "updateComponents": {
          "components": [
            {
              "id": "container",
              "component": "Column",
              "children": ["weight-input", "height-input", "calc-button", "result-text"]
            }
          ]
        }
      }
    ]
  }
}
```
*   **Action**: Store the `calculator_id` to retrieve the schema and execute calculations later.

#### B. Failure/Rejection Event Format
If the agent rejects the prompt (e.g. not calculator related) or fails during the generation loops:
*   **Intent Rejection**:
    ```json
    {
      "content": { "role": "model", "parts": [] },
      "output": {
        "error": "Not a valid calculator request."
      }
    }
    ```
*   **Generation/Validation Failure**:
    ```json
    {
      "content": { "role": "model", "parts": [] },
      "output": {
        "error": "Calculator generation failed, please try again."
      }
    }
    ```

---

### Step 3: Accessing & Executing Generated Calculators

Once a calculator has been created, the consumer application utilizes the dedicated REST endpoints to fetch UI declarations and run the calculation engine.

#### 1. Retrieve the A2UI Schema
Fetch the declarative layout and component validation rules for a specific calculator.
*   **Endpoint**: `GET /schema/{calculator_id}`
*   **Response (HTTP 200 OK)**:
    ```json
    [
      {
        "updateComponents": {
          "components": [
            {
              "id": "container",
              "component": "Column",
              "children": ["weight-input", "height-input", "calc-button", "result-text"]
            },
            {
              "id": "weight-input",
              "component": "TextField",
              "label": "Weight (kg)",
              "value": { "path": "/weight" },
              "checks": [
                {
                  "condition": "numeric(min=0.5, max=15.0)",
                  "message": "Weight must be between 0.5 and 15.0 kg"
                }
              ]
            }
          ]
        }
      }
    ]
    ```
*   **Errors**:
    *   `404 Not Found`: If the `calculator_id` doesn't exist.

#### 2. Evaluate Inputs (Run Calculations)
Submits user input values collected from the form to execute the calculator's business logic.
*   **Endpoint**: `POST /evaluate/{calculator_id}`
*   **Request Body**:
    ```json
    {
      "inputs": {
        "weight": 70,
        "height": 175
      }
    }
    ```
*   **Response (HTTP 200 OK)**:
    ```json
    {
      "outputs": {
        "bmi_result_text": 22.9,
        "category": "normal"
      }
    }
    ```
*   **Response on Validation/Execution Error (HTTP 400 Bad Request)**:
    If the input parameters fail script-defined logic checks, or if runtime division-by-zero occurs:
    ```json
    {
      "detail": "Weight must be positive. Raw Output: ..."
    }
    ```
*   **Errors**:
    *   `404 Not Found`: Calculator ID not found.
    *   `500 Internal Server Error`: Backend calculation script is missing.

