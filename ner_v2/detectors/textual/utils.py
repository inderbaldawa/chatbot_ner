from __future__ import absolute_import

import json
import six

from chatbot_ner.config import ner_logger
from language_utilities.constant import ENGLISH_LANG

from ner_constants import (DATASTORE_VERIFIED, MODEL_VERIFIED,
                           FROM_FALLBACK_VALUE, ORIGINAL_TEXT, ENTITY_VALUE, DETECTION_METHOD,
                           DETECTION_LANGUAGE, ENTITY_VALUE_DICT_KEY)
from ner_v2.detectors.textual.text_detection import TextDetector


def verify_text_request(request):
    """
    Check the request object
    1. If proper message or entity is present in required
    format.

    2. If length of message or entity is in allowed range

    Args:
        request: API request object

    Returns:
        Raises KeyError if message or entities are not present
        Raises TypeError if message is not list or entities is not dict type
        Else Return none
    """

    request_data = json.loads(request.body)
    message = request_data.get("message")
    entities = request_data.get("entities")

    if not message:
        ner_logger.exception("Message param is not passed")
        raise KeyError("Message is required")

    if not entities:
        ner_logger.exception("Entities param is not passed")
        raise KeyError("Entities dict is required")

    if not isinstance(message, list):
        ner_logger.exception("Message param is not in correct format")
        raise TypeError("Message should be in format of list of string")

    if not isinstance(entities, dict):
        ner_logger.exception("Entities param is not in correct format")
        raise TypeError("Entities should be dict of entity details")

    if len(message) > 100:
        ner_logger.exception("Maximum number of message can be 100 for "
                             "bulk detection")
        raise ValueError("Maximum number of message can be 100 for "
                         "bulk detection")

    if len(list(entities)) > 100:
        ner_logger.exception("Maximum number of entities can be 100 for "
                             " detection")
        raise ValueError("Maximum number of entities can be 100 for "
                         "bulk detection")


def get_detection(message, entity_dict, bot_message=None,
                  language=ENGLISH_LANG, target_language_script=ENGLISH_LANG,
                  **kwargs):
    """
    Get text detection for given message on given entities dict using
    TextDetector module.

    If the message is string type call TextDetector.detect() mwthod, if it is list
    call TextDetector.detect_bulk() method. Else, it wol raise an error.
    Args:
        message: message to detect text on
        entity_dict: entity details dict
        structured_value: structured value
        bot_message: bot message
        language: langugae for text detection
        target_language_script: target language for detection default ENGLISH
        **kwargs: other kwargs

    Returns:

        detected entity output
    """
    text_detector = TextDetector(entity_dict=entity_dict, source_language_script=language,
                                 target_language_script=target_language_script)
    if isinstance(message, six.string_types):
        entity_output = text_detector.detect(message=message,
                                             bot_message=bot_message)
    elif isinstance(message, (list, tuple)):
        entity_output = text_detector.detect_bulk(messages=message)
    else:
        raise TypeError('`message` argument must be either of type `str`, `unicode`, `list` or `tuple`.')

    return entity_output


def get_text_entity_detection_data(request):
    """
    Get details of message and entities from request and call get_detection internally
    to get the results.

    Messages to detect text can be of two format:

    1) Single entry in the list of message, for this we use `text_detector.detect` method.
    Also for this case we check if `ignore_message` flag is present.

    2) For multiples message, underlying code will call `text_detector.detect_bulk` method.
    In this case we ignore flag for ignore_message for all the entities.

    Args:
        request: request object
    Returns:
        output data list for all the message
    Examples:
        Request Object:
        {
                    "message": ["I want to go to Jabalpur"],
                    "bot_message": null,
                    "language_script": "en",
                    "source_language": "en",
                    "entities": {
                        "city": {
                            "structured_value": "Delhi",
                            "fallback_value": null,
                            "predetected_values": ["Mumbai"],
                            "fuzziness": null,
                            "min_token_len_fuzziness": null,
                            "ignore_message": false
                        },
                        "restaurant": {
                            "structured_value": null,
                            "fallback_value": null,
                            "predetected_values": null,
                            "fuzziness": null,
                            "min_token_len_fuzziness": null,
                            "ignore_message": false
                                }
                             }
                         }
            output response:
                        [
                            {
                            "entities": {
                                "restaurant": [],
                                "city": [
                                    {
                                        "entity_value": {
                                            "value": "New Delhi",
                                            "datastore_verified": true,
                                            "model_verified": false
                                        },
                                        "detection": "structure_value_verified",
                                        "original_text": "delhi",
                                        "language": "en"
                                    },
                                    {
                                        "entity_value": {
                                            "value": "Mumbai",
                                            "datastore_verified": false,
                                            "model_verified": true
                                        },
                                        "detection": "structure_value_verified",
                                        "original_text": "Mumbai",
                                        "language": "en"
                                    }
                        ]
    """
    request_data = json.loads(request.body)
    message = request_data.get("message", [])
    bot_message = request_data.get("bot_message")
    entities = request_data.get("entities", {})
    target_language_script = request_data.get('language_script') or ENGLISH_LANG
    source_language = request_data.get('source_language') or ENGLISH_LANG

    data = []

    message_len = len(message)

    if message_len == 1:

        # get first message
        message_str = message[0]

        fallback_value_entities = {}
        text_value_entities = {}

        data.append({"entities": {}, "language": source_language})

        for each_entity, value in entities.items():
            ignore_message = value.get('ignore_message', False)

            if ignore_message:
                fallback_value_entities[each_entity] = value
            else:
                text_value_entities[each_entity] = value

        # get detection for text entities which has ignore_message flag
        if fallback_value_entities:
            output = get_output_for_fallback_entities(fallback_value_entities, source_language)
            data[0]["entities"].update(output)

        # get detection for text entities
        output = get_detection(message=message_str, entity_dict=text_value_entities,
                               structured_value=None, bot_message=bot_message,
                               language_script=source_language,
                               target_language_script=target_language_script)
        data[0]["entities"].update(output[0])

    # check if more than one message
    elif len(message) > 1:
        text_detection_result = get_detection(message=message, entity_dict=entities,
                                              structured_value=None, bot_message=bot_message)

        data = [{"entities": x, "language": source_language} for x in text_detection_result]

    else:
        ner_logger.debug("No valid message provided")
        raise KeyError("Message is required")

    return data


def get_output_for_fallback_entities(entities_dict, language=ENGLISH_LANG):
    """
    Generate default detection output for default fallback entities.
    It will check if fallback_value is present if not it will return
    empty list for that entity.

    Args:
        entities_dict: dict of entities details
        language: language to run

    Returns:
        TextDetection output (list of dict) for default fallback values

    Examples:
        Input:
        {
            'city': {'fallback_value': 'Mumbai', 'ignore_message': True},
            'restaurant': {'fallback_value': None, 'ignore_message': True}
        }

        Output:

        {
        'city': [
                    {'entity_value': {'value': 'Mumbai',
                                    'datastore_verified': False,
                                    'model_verified': False},
                    'detection': 'fallback_value',
                    'original_text': 'Mumbai',
                    'language': 'en'}
                ],
        'restaurant': []
        }

    """
    output = {}
    if not entities_dict:
        return output

    for entity, value in entities_dict.items():
        fallback_value = value.get("fallback_value")

        if not fallback_value:
            output[entity] = []

        else:
            output[entity] = [
                {
                    ENTITY_VALUE: {
                        ENTITY_VALUE_DICT_KEY: fallback_value,
                        DATASTORE_VERIFIED: False,
                        MODEL_VERIFIED: False
                    },
                    DETECTION_METHOD: FROM_FALLBACK_VALUE,
                    ORIGINAL_TEXT: fallback_value,
                    DETECTION_LANGUAGE: language
                }
            ]
    return output
