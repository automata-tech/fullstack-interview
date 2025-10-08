from flask import Flask, jsonify, request
from flask_cors import CORS
import redis
import json
import os
import time
from datetime import datetime
import logging
import sys

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app.logger.setLevel(logging.INFO)

# Redis connection
redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))

# Simulated lab devices
DEVICES = {
    'liquid-handler-1': {
        'id': 'liquid-handler-1',
        'name': 'Liquid Handler Alpha',
        'type': 'liquid_handler',
        'status': 'available',
        'capabilities': ['pipette', 'dispense', 'aspirate']
    },
    'incubator-1': {
        'id': 'incubator-1',
        'name': 'Incubator Beta',
        'type': 'incubator',
        'status': 'available',
        'capabilities': ['heat', 'cool', 'shake']
    },
    'plate-reader-1': {
        'id': 'plate-reader-1',
        'name': 'Plate Reader Gamma',
        'type': 'plate_reader',
        'status': 'available',
        'capabilities': ['absorbance', 'fluorescence']
    }
}

def get_device_status(device_id):
    """Get device status from Redis or default"""
    cached = redis_client.get(f'device:{device_id}:status')
    if cached:
        return cached.decode('utf-8')
    return DEVICES.get(device_id, {}).get('status', 'unknown')

def set_device_status(device_id, status, workflow_id=None):
    """Set device status in Redis"""
    redis_client.set(f'device:{device_id}:status', status)
    if workflow_id:
        redis_client.set(f'device:{device_id}:workflow', workflow_id)
    else:
        redis_client.delete(f'device:{device_id}:workflow')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'device-service'})

@app.route('/devices', methods=['GET'])
def list_devices():
    """List all devices with current status"""
    devices = []
    for device_id, device_info in DEVICES.items():
        device = device_info.copy()
        device['status'] = get_device_status(device_id)
        workflow_id = redis_client.get(f'device:{device_id}:workflow')
        if workflow_id:
            device['workflow_id'] = workflow_id.decode('utf-8')
        devices.append(device)
    return jsonify(devices)

@app.route('/devices/<device_id>', methods=['GET'])
def get_device(device_id):
    """Get specific device details"""
    if device_id not in DEVICES:
        return jsonify({'error': 'Device not found'}), 404

    device = DEVICES[device_id].copy()
    device['status'] = get_device_status(device_id)
    workflow_id = redis_client.get(f'device:{device_id}:workflow')
    if workflow_id:
        device['workflow_id'] = workflow_id.decode('utf-8')

    return jsonify(device)

@app.route('/devices/<device_id>/book', methods=['POST'])
def book_device(device_id):
    """Book a device for a workflow"""
    if device_id not in DEVICES:
        logger.warning(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404

    data = request.json
    workflow_id = data.get('workflow_id')

    if not workflow_id:
        logger.error("Booking request missing workflow_id")
        return jsonify({'error': 'workflow_id required'}), 400

    logger.info(f"Attempting to book device {device_id} for workflow {workflow_id}")

    current_status = get_device_status(device_id)

    if current_status != 'available':
        logger.warning(f"Device {device_id} is not available (status: {current_status})")
        return jsonify({'error': 'Device is not available'}), 409

    time.sleep(0.1)

    set_device_status(device_id, 'busy', workflow_id)

    logger.info(f"Device {device_id} successfully booked by workflow {workflow_id}")
    return jsonify({
        'device_id': device_id,
        'status': 'busy',
        'workflow_id': workflow_id,
        'booked_at': datetime.utcnow().isoformat()
    })

@app.route('/devices/<device_id>/release', methods=['POST'])
def release_device(device_id):
    """Release a device from a workflow"""
    if device_id not in DEVICES:
        logger.warning(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404

    data = request.json
    workflow_id = data.get('workflow_id')

    logger.info(f"Attempting to release device {device_id} from workflow {workflow_id}")

    current_workflow = redis_client.get(f'device:{device_id}:workflow')
    if current_workflow and current_workflow.decode('utf-8') != workflow_id:
        logger.warning(f"Device {device_id} is booked by another workflow")
        return jsonify({'error': 'Device is booked by another workflow'}), 403

    set_device_status(device_id, 'available')

    logger.info(f"Device {device_id} released successfully")
    return jsonify({
        'device_id': device_id,
        'status': 'available',
        'released_at': datetime.utcnow().isoformat()
    })

@app.route('/devices/<device_id>/execute', methods=['POST'])
def execute_operation(device_id):
    """Execute an operation on a device"""
    if device_id not in DEVICES:
        logger.warning(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404

    data = request.json
    operation = data.get('operation')
    workflow_id = data.get('workflow_id')

    logger.info(f"Executing operation '{operation}' on device {device_id} for workflow {workflow_id}")

    current_workflow = redis_client.get(f'device:{device_id}:workflow')
    if not current_workflow or current_workflow.decode('utf-8') != workflow_id:
        logger.warning(f"Device {device_id} not booked by workflow {workflow_id}")
        return jsonify({'error': 'Device not booked by this workflow'}), 403

    time.sleep(0.5)

    logger.info(f"Operation '{operation}' completed on device {device_id}")
    return jsonify({
        'device_id': device_id,
        'operation': operation,
        'status': 'completed',
        'executed_at': datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    # Initialize device statuses in Redis
    for device_id in DEVICES:
        if not redis_client.exists(f'device:{device_id}:status'):
            set_device_status(device_id, 'available')

    app.run(host='0.0.0.0', port=5001, debug=False)
