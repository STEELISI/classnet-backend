'''antAPI datasets client calls'''

import requests

from .auth import AntAPIClientAuthenticator

from .errors import (
    AntAPIClientTracError,
)

def antapi_datasets_meta_new(auth: AntAPIClientAuthenticator, timeout=10,
                             **kwmetadata_fields) -> None:
    '''Create a new dataset metadata.

    :param auth:        An instance of AntAPIClientAuthenticator
    :type auth:         AntAPIClientAuthenticator
    :param kwmetadata_fields: metadata fields

    **Required fields**
    - datasetName
    - shortDesc
    - longDesc
    - availabilityStartDateTime
    - availabilityEndDateTime
    - collectionStartDateTime
    - collectionEndDateTime
    - byteSize
    - keywordList
    - anonymizationList
    - providerName
    - useAgreement

    :returns: None

    :raises: AntAPIClientTracError
    '''
    meta_new_url = auth.base_url + '/datasets/meta/new'

    # xxx add validation

    json_data = {}
    # convert DateTime fields to iso
    for key, val in kwmetadata_fields.items():
        if not key.endswith('DateTime'):
            json_data[key] = val
            continue
        try:
            json_data[key] = val.isoformat()
        except Exception as ex: # pylint: disable=broad-except
            raise AntAPIClientTracError(
                f"Can't convert datetime field {key} = {val} to ISO time format"
            ) from ex

    json_reply = {}
    try:
        res = requests.post(meta_new_url, json=json_data,
                            headers=auth.auth_header(), timeout=timeout)
        res.raise_for_status()
        json_reply = res.json()

    except Exception as ex: # pylint: disable=broad-except
        if not isinstance(json_reply, dict):
            json_reply = {}
        raise AntAPIClientTracError(
            f"Can't submit request: status={res.status_code}, "
            f"error={json_reply.get('message', 'None')}"
        ) from ex
