# Solution Guide for Interviewers

## Overview

This guide provides solutions to all intentional bugs and the feature implementation for the Lab Automation System exercise.

## Phase 1: Debugging - Solutions

### Bug 1: Missing Environment Variable (workflow-service crashes)

**Location**: `docker-compose.yml` and `services/workflow-service/app.py:17`

**Symptom**: `workflow-service` fails to start with `KeyError: 'DEVICE_API_URL'`

**Root Cause**: The `DEVICE_API_URL` environment variable is not defined in docker-compose.yml

**Fix**: Add to `docker-compose.yml` under `workflow-service` → `environment`:
```yaml
- DEVICE_API_URL=http://device-service:5001
```

**Evaluation Points**:
- ✅ Checks docker-compose logs
- ✅ Identifies missing environment variable from error message
- ✅ Understands service-to-service communication in Docker network

---

### Bug 2: Wrong API Endpoint Path

**Location**: `services/workflow-service/app.py:90-92`

**Symptom**: Starting a workflow returns 404 error when trying to book device

**Root Cause**: Calling wrong endpoint `/device/{id}/reserve` instead of `/devices/{id}/book`

**Fix**: Change line 90-92 in `workflow-service/app.py`:
```python
# FROM:
response = requests.post(
    f'{DEVICE_API_URL}/device/{device_id}/reserve',  # Wrong path!
    json={'workflow_id': workflow_id},
    timeout=5
)

# TO:
response = requests.post(
    f'{DEVICE_API_URL}/devices/{device_id}/book',
    json={'workflow_id': workflow_id},
    timeout=5
)
```

**Evaluation Points**:
- ✅ Uses browser DevTools or checks workflow-service logs
- ✅ Identifies 404 error
- ✅ Compares with device-service API endpoints
- ✅ Understands REST API conventions

---

### Bug 3: Race Condition in Device Booking

**Location**: `services/device-service/app.py:70-91`

**Symptom**: Multiple workflows can book the same device simultaneously when requests arrive concurrently

**Root Cause**: No atomic check-and-set operation. The code reads status, waits (simulating processing), then sets status - allowing race conditions.

**Fix**: Use Redis atomic operations. Replace the book_device function:

```python
@app.route('/devices/<device_id>/book', methods=['POST'])
def book_device(device_id):
    """Book a device for a workflow using atomic Redis operations"""
    if device_id not in DEVICES:
        return jsonify({'error': 'Device not found'}), 404

    data = request.json
    workflow_id = data.get('workflow_id')

    if not workflow_id:
        return jsonify({'error': 'workflow_id required'}), 400

    # Use Redis SETNX for atomic check-and-set
    lock_key = f'device:{device_id}:lock'
    if not redis_client.set(lock_key, workflow_id, nx=True, ex=300):
        return jsonify({'error': 'Device is not available'}), 409

    set_device_status(device_id, 'busy', workflow_id)

    return jsonify({
        'device_id': device_id,
        'status': 'busy',
        'workflow_id': workflow_id,
        'booked_at': datetime.utcnow().isoformat()
    })
```

And update the release function to remove the lock:
```python
@app.route('/devices/<device_id>/release', methods=['POST'])
def release_device(device_id):
    """Release a device from a workflow"""
    if device_id not in DEVICES:
        return jsonify({'error': 'Device not found'}), 404

    data = request.json
    workflow_id = data.get('workflow_id')

    # Verify the workflow owns this device
    current_workflow = redis_client.get(f'device:{device_id}:workflow')
    if current_workflow and current_workflow.decode('utf-8') != workflow_id:
        return jsonify({'error': 'Device is booked by another workflow'}), 403

    set_device_status(device_id, 'available')
    redis_client.delete(f'device:{device_id}:lock')  # Release lock

    return jsonify({
        'device_id': device_id,
        'status': 'available',
        'released_at': datetime.utcnow().isoformat()
    })
```

**Evaluation Points**:
- ✅ Identifies the race condition (may require testing or code review)
- ✅ Understands distributed systems challenges
- ✅ Knows about atomic operations (SETNX, compare-and-swap, etc.)
- ✅ Implements proper locking mechanism

**Alternative Solutions** (also acceptable):
- Database transactions with SELECT FOR UPDATE
- Distributed locks (Redis SETNX, Redlock)
- Optimistic locking with version numbers

---

### Bug 4: Stale Device Status in Frontend

**Location**: `frontend/src/components/DeviceList.js:6-29`

**Symptom**: Device status in UI doesn't update when device becomes busy or available

**Root Cause**: Component caches device status on first render and never updates the cache

**Fix**: Remove the caching logic and use the actual device data:

```javascript
import React from 'react';
import './DeviceList.css';

function DeviceList({ devices }) {
  const getStatusColor = (status) => {
    switch (status) {
      case 'available':
        return '#4caf50';
      case 'busy':
        return '#ff9800';
      default:
        return '#999';
    }
  };

  return (
    <div className="device-list">
      {devices.length === 0 ? (
        <p className="empty-state">No devices available</p>
      ) : (
        devices.map((device) => (
          <div key={device.id} className="device-card">
            <div className="device-header">
              <h3>{device.name}</h3>
              <span
                className="status-badge"
                style={{ backgroundColor: getStatusColor(device.status) }}
              >
                {device.status}
              </span>
            </div>
            <div className="device-details">
              <p><strong>Type:</strong> {device.type}</p>
              <p><strong>ID:</strong> {device.id}</p>
              {device.workflow_id && (
                <p><strong>Workflow:</strong> {device.workflow_id}</p>
              )}
              {device.capabilities && (
                <div className="capabilities">
                  <strong>Capabilities:</strong>
                  <div className="capability-tags">
                    {device.capabilities.map((cap) => (
                      <span key={cap} className="capability-tag">
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default DeviceList;
```

**Evaluation Points**:
- ✅ Notices UI doesn't update despite data changing
- ✅ Inspects React component state and props
- ✅ Identifies unnecessary caching
- ✅ Understands React rendering and props updates

---

### Bug 5: Missing Sample Validation

**Location**: `services/workflow-service/app.py:58-86`

**Symptom**: Workflows can be created with non-existent sample barcodes

**Root Cause**: The create_workflow endpoint doesn't validate that samples exist

**Fix**: Add validation before creating workflow:

```python
@app.route('/workflows', methods=['POST'])
def create_workflow():
    """Create a new workflow with sample validation"""
    data = request.json

    workflow_id = str(uuid.uuid4())
    name = data.get('name')
    device_id = data.get('device_id')
    sample_barcodes = data.get('sample_barcodes', [])
    steps = data.get('steps', [])

    if not name or not device_id:
        return jsonify({'error': 'name and device_id are required'}), 400

    # Validate samples exist
    if sample_barcodes:
        try:
            response = requests.post(
                f'{SAMPLE_API_URL}/samples/validate',
                json={'barcodes': sample_barcodes},
                timeout=5
            )
            if response.status_code == 200:
                results = response.json()
                invalid_samples = [r['barcode'] for r in results if not r['exists']]
                if invalid_samples:
                    return jsonify({
                        'error': 'Invalid sample barcodes',
                        'invalid_samples': invalid_samples
                    }), 400
        except requests.exceptions.RequestException as e:
            return jsonify({'error': f'Failed to validate samples: {str(e)}'}), 500

    workflow = {
        'id': workflow_id,
        'name': name,
        'device_id': device_id,
        'sample_barcodes': sample_barcodes,
        'steps': steps,
        'status': 'created',
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }

    workflows = get_all_workflows()
    workflows[workflow_id] = workflow
    save_workflows(workflows)

    return jsonify(workflow), 201
```

**Evaluation Points**:
- ✅ Identifies missing validation (may discover through testing)
- ✅ Uses existing sample-service API
- ✅ Proper error handling
- ✅ Returns meaningful error messages

---

## Phase 2: Feature Implementation - Solution

### Workflow Pause/Resume Feature

#### Backend Implementation (`workflow-service/app.py`)

Add two new endpoints:

```python
@app.route('/workflows/<workflow_id>/pause', methods=['POST'])
def pause_workflow(workflow_id):
    """Pause a running workflow and release device"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404

    if workflow['status'] != 'running':
        return jsonify({'error': 'Workflow is not running'}), 400

    device_id = workflow['device_id']

    try:
        # Release the device
        response = requests.post(
            f'{DEVICE_API_URL}/devices/{device_id}/release',
            json={'workflow_id': workflow_id},
            timeout=5
        )

        if response.status_code != 200:
            return jsonify({
                'error': 'Failed to release device',
                'details': response.json()
            }), response.status_code

        # Update workflow status
        workflow['status'] = 'paused'
        workflow['paused_at'] = datetime.utcnow().isoformat() + 'Z'
        update_workflow(workflow_id, workflow)

        return jsonify(workflow)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to communicate with device service: {str(e)}'}), 500


@app.route('/workflows/<workflow_id>/resume', methods=['POST'])
def resume_workflow(workflow_id):
    """Resume a paused workflow by re-booking device"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404

    if workflow['status'] != 'paused':
        return jsonify({'error': 'Workflow is not paused'}), 400

    device_id = workflow['device_id']

    try:
        # Re-book the device
        response = requests.post(
            f'{DEVICE_API_URL}/devices/{device_id}/book',
            json={'workflow_id': workflow_id},
            timeout=5
        )

        if response.status_code != 200:
            return jsonify({
                'error': 'Failed to book device',
                'details': response.json()
            }), response.status_code

        # Update workflow status
        workflow['status'] = 'running'
        workflow['resumed_at'] = datetime.utcnow().isoformat() + 'Z'
        update_workflow(workflow_id, workflow)

        return jsonify(workflow)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to communicate with device service: {str(e)}'}), 500
```

#### Frontend Implementation

**Update `App.js`**: Add pause/resume handlers

```javascript
const handlePauseWorkflow = async (workflowId) => {
  try {
    await axios.post(`${WORKFLOW_API}/workflows/${workflowId}/pause`);
    await fetchData();
  } catch (err) {
    console.error('Error pausing workflow:', err);
    alert(`Failed to pause workflow: ${err.response?.data?.error || err.message}`);
  }
};

const handleResumeWorkflow = async (workflowId) => {
  try {
    await axios.post(`${WORKFLOW_API}/workflows/${workflowId}/resume`);
    await fetchData();
  } catch (err) {
    console.error('Error resuming workflow:', err);
    alert(`Failed to resume workflow: ${err.response?.data?.error || err.message}`);
  }
};

// Pass to WorkflowList component
<WorkflowList
  workflows={workflows}
  onStart={handleStartWorkflow}
  onComplete={handleCompleteWorkflow}
  onPause={handlePauseWorkflow}
  onResume={handleResumeWorkflow}
/>
```

**Update `WorkflowList.js`**: Add pause/resume buttons

```javascript
function WorkflowList({ workflows, onStart, onComplete, onPause, onResume }) {
  const getStatusColor = (status) => {
    switch (status) {
      case 'created':
        return '#2196f3';
      case 'running':
        return '#ff9800';
      case 'paused':
        return '#9c27b0';  // New color for paused state
      case 'completed':
        return '#4caf50';
      default:
        return '#999';
    }
  };

  // ... rest of component

  <div className="workflow-actions">
    {workflow.status === 'created' && (
      <button onClick={() => onStart(workflow.id)} className="start-btn">
        Start Workflow
      </button>
    )}
    {workflow.status === 'running' && (
      <>
        <button onClick={() => onPause(workflow.id)} className="pause-btn">
          Pause Workflow
        </button>
        <button onClick={() => onComplete(workflow.id)} className="complete-btn">
          Complete Workflow
        </button>
      </>
    )}
    {workflow.status === 'paused' && (
      <button onClick={() => onResume(workflow.id)} className="resume-btn">
        Resume Workflow
      </button>
    )}
  </div>
}
```

**Add CSS for new buttons** (`WorkflowList.css`):

```css
.pause-btn {
  background: #ff9800;
  color: white;
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}

.pause-btn:hover {
  background: #f57c00;
}

.resume-btn {
  background: #9c27b0;
  color: white;
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}

.resume-btn:hover {
  background: #7b1fa2;
}
```

**Evaluation Points**:
- ✅ Implements both backend endpoints correctly
- ✅ Properly releases/re-books device
- ✅ Updates workflow status appropriately
- ✅ Handles errors gracefully (e.g., device not available on resume)
- ✅ Updates frontend UI with pause/resume buttons
- ✅ Tests complete flow end-to-end
- ✅ Code is clean and maintainable

---

## Testing the Exercise

### Pre-Exercise Checklist
- [ ] All services start correctly after fixing Bug 1
- [ ] Workflows can be created
- [ ] Workflows fail to start (Bug 2 present)
- [ ] Device status doesn't update in UI (Bug 4 present)
- [ ] Race condition can be triggered with concurrent requests (Bug 3)

### Post-Exercise Validation

Run through this flow to verify all bugs are fixed:

1. Start all services: `docker-compose up`
2. Create a workflow with a valid device
3. Start the workflow → should succeed
4. Check device status in UI → should show "busy"
5. Complete the workflow → should succeed
6. Check device status → should show "available"
7. Test concurrent bookings (optional, for Bug 3)

---

## Interview Tips

### What to Look For

**Excellent Candidate**:
- Systematically checks logs and identifies issues
- Fixes bugs in logical order (environment → API → race condition)
- Implements clean, well-tested pause/resume feature
- Asks clarifying questions about requirements
- Explains their thought process clearly
- Shows understanding of distributed systems

**Good Candidate**:
- Finds and fixes most bugs
- Implements working pause/resume feature
- May need hints for race condition
- Code works but could be cleaner

**Needs Improvement**:
- Struggles to identify bugs without significant help
- Random debugging approach (trial and error)
- Incomplete feature implementation
- Doesn't test their changes

### Time Management

Typical breakdown for a strong candidate:
- Bug 1 (env var): 5 minutes
- Bug 2 (wrong endpoint): 5-10 minutes
- Bug 4 (frontend cache): 10-15 minutes
- Bug 3 (race condition): 10-20 minutes
- Pause/Resume feature: 25-40 minutes

If time is running short, you can:
- Skip Bug 3 (race condition) - it's the most complex
- Reduce scope of pause/resume (backend only)
- Provide hints more liberally

### Discussion Questions

After the exercise, consider asking:
- "How would you monitor this system in production?"
- "What would you do differently if this scaled to 100 devices?"
- "How would you handle device failures during workflow execution?"
- "What tests would you write for this system?"
