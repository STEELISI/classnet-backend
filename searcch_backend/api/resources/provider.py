# providerlist.py

from flask import jsonify
from flask_restful import Resource
from searcch_backend.api.app import db
from searcch_backend.models.model import DUA
import logging

LOG = logging.getLogger(__name__)

class Provider(Resource):
    def get(self):
        LOG.error("here")
        try:
            providers = db.session.query(DUA.provider).distinct().all()
            provider_list = [provider[0] for provider in providers]
            response = jsonify(provider_list)
            response.status_code=200
            return response
        except Exception as e:
            LOG.error(f"Error fetching providers: {e}")
            response = jsonify({'error': 'An error occurred while fetching providers'})
            response.status_code = 500
            return response
