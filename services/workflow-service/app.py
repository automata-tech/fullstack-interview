from flask import Flask, jsonify, request
from flask_cors import CORS
import redis
import json
import os
import requests
from datetime import datetime
import uuid
import logging
import sys
from enum import Enum

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app.logger.setLevel(logging.INFO)

# Workflow status enum
class WorkflowStatus(str, Enum):
    CREATED = 'created'
    RUNNING = 'running'
    COMPLETED = 'completed'
    PAUSED = 'paused'

# Redis connection
redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))

DEVICE_API_URL = os.environ['DEVICE_API_URL']
SAMPLE_API_URL = os.getenv('SAMPLE_API_URL', 'http://localhost:5002')

WORKFLOWS_KEY = 'workflows'

def get_all_workflows():
    """Get all workflows from Redis"""
    workflows_data = redis_client.get(WORKFLOWS_KEY)
    if workflows_data:
        return json.loads(workflows_data)
    return {}

def save_workflows(workflows):
    """Save workflows to Redis"""
    redis_client.set(WORKFLOWS_KEY, json.dumps(workflows))

def get_workflow(workflow_id):
    """Get a specific workflow"""
    workflows = get_all_workflows()
    return workflows.get(workflow_id)

def update_workflow(workflow_id, updates):
    """Update a workflow"""
    workflows = get_all_workflows()
    if workflow_id in workflows:
        workflows[workflow_id].update(updates)
        save_workflows(workflows)
        return workflows[workflow_id]
    return None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'workflow-service'})

@app.route('/workflows', methods=['GET'])
def list_workflows():
    """List all workflows"""
    workflows = get_all_workflows()
    return jsonify(list(workflows.values()))

@app.route('/workflows/<workflow_id>', methods=['GET'])
def get_workflow_route(workflow_id):
    """Get specific workflow"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    return jsonify(workflow)

@app.route('/workflows', methods=['POST'])
def create_workflow():
    """Create a new workflow"""
    data = request.json

    workflow_id = str(uuid.uuid4())
    name = data.get('name')
    device_id = data.get('device_id')
    sample_barcodes = data.get('sample_barcodes', [])
    steps = data.get('steps', [])

    if not name or not device_id:
        return jsonify({'error': 'name and device_id are required'}), 400

    logger.info(f"Creating workflow: {name} (ID: {workflow_id}) for device: {device_id}")

    workflow = {
        'id': workflow_id,
        'name': name,
        'device_id': device_id,
        'sample_barcodes': sample_barcodes,
        'steps': steps,
        'status': WorkflowStatus.CREATED.value,
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }

    workflows = get_all_workflows()
    workflows[workflow_id] = workflow
    save_workflows(workflows)

    logger.info(f"Workflow {workflow_id} created successfully")
    return jsonify(workflow), 201

@app.route('/workflows/<workflow_id>/start', methods=['POST'])
def start_workflow(workflow_id):
    """Start a workflow - books device and begins execution"""
    logger.info(f"Starting workflow: {workflow_id}")

    workflow = get_workflow(workflow_id)
    if not workflow:
        logger.error(f"Workflow not found: {workflow_id}")
        return jsonify({'error': 'Workflow not found'}), 404

    if workflow['status'] != WorkflowStatus.CREATED.value:
        logger.warning(f"Workflow {workflow_id} already started or completed")
        return jsonify({'error': 'Workflow already started or completed'}), 400

    device_id = workflow['device_id']
    logger.info(f"Booking device {device_id} for workflow {workflow_id}")

    try:
        response = requests.post(
            f'{DEVICE_API_URL}/device/{device_id}/reserve',
            json={'workflow_id': workflow_id},
            timeout=5
        )

        if response.status_code != 200:
            logger.error(f"Failed to book device {device_id}: {response.status_code} - {response.text}")
            return jsonify({
                'error': 'Failed to book device',
                'details': response.json()
            }), response.status_code

        workflow['status'] = WorkflowStatus.RUNNING.value
        workflow['started_at'] = datetime.utcnow().isoformat() + 'Z'
        update_workflow(workflow_id, workflow)

        logger.info(f"Workflow {workflow_id} started successfully")
        return jsonify(workflow)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with device service: {str(e)}")
        return jsonify({'error': f'Failed to communicate with device service: {str(e)}'}), 500

@app.route('/workflows/<workflow_id>/complete', methods=['POST'])
def complete_workflow(workflow_id):
    """Complete a workflow and release device"""
    logger.info(f"Completing workflow: {workflow_id}")

    workflow = get_workflow(workflow_id)
    if not workflow:
        logger.error(f"Workflow not found: {workflow_id}")
        return jsonify({'error': 'Workflow not found'}), 404

    if workflow['status'] != WorkflowStatus.RUNNING.value:
        logger.warning(f"Workflow {workflow_id} is not running")
        return jsonify({'error': 'Workflow is not running'}), 400

    device_id = workflow['device_id']
    logger.info(f"Releasing device {device_id} from workflow {workflow_id}")

    try:
        response = requests.post(
            f'{DEVICE_API_URL}/devices/{device_id}/release',
            json={'workflow_id': workflow_id},
            timeout=5
        )

        if response.status_code != 200:
            logger.error(f"Failed to release device {device_id}: {response.status_code}")
            return jsonify({
                'error': 'Failed to release device',
                'details': response.json()
            }), response.status_code

        workflow['status'] = WorkflowStatus.COMPLETED.value
        workflow['completed_at'] = datetime.utcnow().isoformat() + 'Z'
        update_workflow(workflow_id, workflow)

        logger.info(f"Workflow {workflow_id} completed successfully")
        return jsonify(workflow)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with device service: {str(e)}")
        return jsonify({'error': f'Failed to communicate with device service: {str(e)}'}), 500

@app.route('/workflows/<workflow_id>/execute-step', methods=['POST'])
def execute_step(workflow_id):
    """Execute a specific step in the workflow"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404

    if workflow['status'] != WorkflowStatus.RUNNING.value:
        return jsonify({'error': 'Workflow is not running'}), 400

    data = request.json
    step_index = data.get('step_index', 0)
    steps = workflow.get('steps', [])

    if step_index >= len(steps):
        return jsonify({'error': 'Invalid step index'}), 400

    step = steps[step_index]
    device_id = workflow['device_id']

    try:
        # Execute operation on device
        response = requests.post(
            f'{DEVICE_API_URL}/devices/{device_id}/execute',
            json={
                'workflow_id': workflow_id,
                'operation': step
            },
            timeout=10
        )

        if response.status_code != 200:
            return jsonify({
                'error': 'Failed to execute step',
                'details': response.json()
            }), response.status_code

        return jsonify({
            'workflow_id': workflow_id,
            'step_index': step_index,
            'step': step,
            'result': response.json()
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to communicate with device service: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)
