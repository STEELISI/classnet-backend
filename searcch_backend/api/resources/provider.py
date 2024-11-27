# providerlist.py

from flask import jsonify, request,abort
from flask_restful import Resource
from searcch_backend.api.app import db
from searcch_backend.models.model import DUA
import logging
from searcch_backend.api.common.auth import (verify_api_key, has_api_key, has_token, verify_token)

LOG = logging.getLogger(__name__)

class Provider(Resource):
    def get(self):
        if has_api_key(request):
            verify_api_key(request)
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not (login_session):
            abort(400, description="insufficient permission to access Contribute Datasets page")
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
        
class ProviderCollection(Resource):
    def get(self):
        if has_api_key(request):
            verify_api_key(request)
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not (login_session):
            abort(400, description="insufficient permission to access Contribute Datasets page")
        try:
            provider_collection_list = db.session.query(DUA.provider,DUA.collection).distinct().all()
            result = []
            result = [{"provider": provider_collection.provider, "collection":provider_collection.collection } for provider_collection in provider_collection_list] 
            response = jsonify(result)
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.status_code=200
            return response
        except Exception as e:
            LOG.error(f"Error fetching providers: {e}")
            response = jsonify({'error': 'An error occurred while fetching providers'})
            response.status_code = 500
            return response

