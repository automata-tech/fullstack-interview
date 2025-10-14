from flask import Flask, jsonify, request
from flask_cors import CORS
import redis
import json
import os
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

# Sample data structure: barcode -> sample info
SAMPLES_KEY = 'samples'

def get_all_samples():
    """Get all samples from Redis"""
    samples_data = redis_client.get(SAMPLES_KEY)
    if samples_data:
        return json.loads(samples_data)
    return {}

def save_samples(samples):
    """Save samples to Redis"""
    redis_client.set(SAMPLES_KEY, json.dumps(samples))

def initialize_samples():
    """Initialize with some sample data"""
    samples = {
        'SAMPLE001': {
            'barcode': 'SAMPLE001',
            'name': 'Blood Sample A',
            'type': 'blood',
            'location': {'plate': 'PLATE-01', 'well': 'A1'},
            'created_at': '2025-01-15T10:00:00Z'
        },
        'SAMPLE002': {
            'barcode': 'SAMPLE002',
            'name': 'Tissue Sample B',
            'type': 'tissue',
            'location': {'plate': 'PLATE-01', 'well': 'A2'},
            'created_at': '2025-01-15T10:05:00Z'
        },
        'SAMPLE003': {
            'barcode': 'SAMPLE003',
            'name': 'Saliva Sample C',
            'type': 'saliva',
            'location': {'plate': 'PLATE-02', 'well': 'B1'},
            'created_at': '2025-01-15T10:10:00Z'
        }
    }
    save_samples(samples)
    return samples

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'sample-service'})

@app.route('/samples', methods=['GET'])
def list_samples():
    """List all samples"""
    samples = get_all_samples()
    return jsonify(list(samples.values()))

@app.route('/samples/<barcode>', methods=['GET'])
def get_sample(barcode):
    """Get specific sample by barcode"""
    samples = get_all_samples()
    sample = samples.get(barcode)

    if not sample:
        return jsonify({'error': 'Sample not found'}), 404

    return jsonify(sample)

@app.route('/samples', methods=['POST'])
def create_sample():
    """Create a new sample"""
    data = request.json

    barcode = data.get('barcode')
    if not barcode:
        logger.error("Sample creation missing barcode")
        return jsonify({'error': 'barcode is required'}), 400

    samples = get_all_samples()

    if barcode in samples:
        logger.warning(f"Sample already exists: {barcode}")
        return jsonify({'error': 'Sample already exists'}), 409

    logger.info(f"Creating sample: {barcode}")

    sample = {
        'barcode': barcode,
        'name': data.get('name', ''),
        'type': data.get('type', ''),
        'location': data.get('location', {}),
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }

    samples[barcode] = sample
    save_samples(samples)

    logger.info(f"Sample {barcode} created successfully")
    return jsonify(sample), 201

@app.route('/samples/<barcode>/location', methods=['PUT'])
def update_sample_location(barcode):
    """Update sample location"""
    samples = get_all_samples()

    if barcode not in samples:
        return jsonify({'error': 'Sample not found'}), 404

    data = request.json
    location = data.get('location')

    if not location:
        return jsonify({'error': 'location is required'}), 400

    samples[barcode]['location'] = location
    samples[barcode]['updated_at'] = datetime.utcnow().isoformat() + 'Z'
    save_samples(samples)

    return jsonify(samples[barcode])

@app.route('/samples/validate', methods=['POST'])
def validate_samples():
    """Validate if samples exist (batch validation)"""
    data = request.json
    barcodes = data.get('barcodes', [])

    if not barcodes:
        logger.error("Validation request missing barcodes")
        return jsonify({'error': 'barcodes array is required'}), 400

    logger.info(f"Validating {len(barcodes)} sample(s)")

    samples = get_all_samples()
    results = []

    for barcode in barcodes:
        exists = barcode in samples
        results.append({
            'barcode': barcode,
            'exists': exists
        })
        if not exists:
            logger.warning(f"Sample not found: {barcode}")

    return jsonify(results)

if __name__ == '__main__':
    # Initialize sample data if not exists
    if not get_all_samples():
        initialize_samples()

    app.run(host='0.0.0.0', port=5002, debug=False)
