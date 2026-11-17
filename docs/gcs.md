# Publishing results to Google Cloud Storage

The results contract is location-independent. To publish to a bucket as well as (or instead of) the
`results/` folder, the job needs a bucket and a way to log in. These commands are a starting point written
from the vendors' guides; check them against the linked pages before running, because cloud CLIs change.

- Keyless login from GitHub Actions: <https://github.com/google-github-actions/auth>
- Reading a bucket from Streamlit: <https://docs.streamlit.io/develop/tutorials/databases/gcs>

## 1. Bucket with object versioning

Versioning keeps every overwritten file, which is what makes the paper record auditable in a bucket.

```bash
export PROJECT_ID=<your-project>
export BUCKET=<your-bucket>
gcloud storage buckets create gs://$BUCKET --project=$PROJECT_ID --location=europe-west1 --uniform-bucket-level-access
gcloud storage buckets update gs://$BUCKET --versioning
```

## 2. Let this repository's workflow write to it, without a key file

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud iam workload-identity-pools create github --project=$PROJECT_ID --location=global
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --project=$PROJECT_ID --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == 'Jefersolitario'"
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --role=roles/storage.objectUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/Jefersolitario/fear-greed-strategy"
```

## 3. Workflow changes

Add `id-token: write` to `permissions`, install with `pip install -e ".[gcs]"`, and add before the run step:

```yaml
      - uses: google-github-actions/auth@v2   # use the current major version from the action's README
        with:
          workload_identity_provider: projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-actions
```

Then publish to both places:

```yaml
      - run: python -m fng.cli run --fetch
      - run: python -m fng.cli run --out gs://<bucket>/fear-greed-strategy
```

## 4. Dashboard

Create a read-only service account (`roles/storage.objectViewer` on the bucket), put its JSON key in the
dashboard's secrets under `[gcp_service_account]`, and change this strategy's `root` in the dashboard's
`strategies.toml` to `gs://<bucket>/fear-greed-strategy`.

## Layout for many strategies

One bucket, one prefix per source repository:

```
gs://<bucket>/fear-greed-strategy/index.json
gs://<bucket>/fear-greed-strategy/fng10_hold/daily.parquet
gs://<bucket>/gb-pair-trading/index.json
...
```

Intraday strategies should still publish `daily.parquet` at the daily grain for the portfolio view. Keep
fills and order-level data in separate, date-partitioned files next to it (`trades/date=YYYY-MM-DD.parquet`);
the dashboard ignores files it does not know.
