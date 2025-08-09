from googleapiclient import discovery

from .config import CONFIG as _CONFIG

client = discovery.build(
    "commentanalyzer",
    "v1alpha1",
    discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
    static_discovery=False,
    developerKey=_CONFIG["google"]["GCP.API_KEY"]
)

def get_perspective(text):
    analyze_request = {
        'comment': {'text': text},
        'requestedAttributes': {'TOXICITY': {}}
    }
    response = client.comments().analyze(body=analyze_request).execute()

    return response
