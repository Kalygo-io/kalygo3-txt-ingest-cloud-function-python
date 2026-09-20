# TLDR

# 

- `https://console.cloud.google.com/cloudpubsub/topic/create?project=command-labs`
- called `qna-ingest-topic`

#

enable GCP API [cloudfunctions.googleapis.com] on project
enable GCP API [eventarc.googleapis.com] on project

#

```sh
gcloud functions deploy process-txt-ingest-topic-message-python \
--gen2 \
--runtime=python312 \
--region=us-east1 \
--source=. \
--entry-point=process_txt_ingest_topic_message \
--trigger-topic=txt-ingest-topic \
--memory=1GB \
--timeout=540s \
--max-instances=10
```