# Généré par DevOps Builder — à relire avant usage.

provider "google" {
  project = var.gcp_project_id
  region  = "europe-west9"
}

# --- Google Artifact Registry
resource "google_artifact_registry_repository" "app" {
  location      = "europe-west9"
  repository_id = "mon-app"
  format        = "DOCKER"
}

# --- Google Cloud Storage
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Google Cloud Run functions
data "archive_file" "function_placeholder" {
  type        = "zip"
  output_path = "${path.module}/function-placeholder.zip"

  source {
    content  = "import functions_framework\n\n\n@functions_framework.http\ndef handler(request):\n    return \"Code à déployer par la CI\"\n"
    filename = "main.py"
  }

  source {
    content  = "functions-framework==3.*\n"
    filename = "requirements.txt"
  }
}

resource "google_storage_bucket" "function_source" {
  name                        = "${var.gcp_project_id}-mon-app-fn-src"
  location                    = "europe-west9"
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_object" "function_placeholder" {
  name   = "placeholder-${data.archive_file.function_placeholder.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_placeholder.output_path
}

resource "google_cloudfunctions2_function" "fn_staging" {
  name     = "mon-app-staging"
  location = "europe-west9"

  build_config {
    runtime     = "python313"
    entry_point = "handler"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_placeholder.name
      }
    }
  }

  service_config {
    available_memory = "256M"
    timeout_seconds  = 30
  }

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {
    ignore_changes = [build_config[0].source]
  }
}

resource "google_cloud_run_service_iam_member" "fn_staging_public" {
  location = google_cloudfunctions2_function.fn_staging.location
  service  = google_cloudfunctions2_function.fn_staging.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloudfunctions2_function" "fn_production" {
  name     = "mon-app"
  location = "europe-west9"

  build_config {
    runtime     = "python313"
    entry_point = "handler"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_placeholder.name
      }
    }
  }

  service_config {
    available_memory = "256M"
    timeout_seconds  = 30
  }

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {
    ignore_changes = [build_config[0].source]
  }
}

resource "google_cloud_run_service_iam_member" "fn_production_public" {
  location = google_cloudfunctions2_function.fn_production.location
  service  = google_cloudfunctions2_function.fn_production.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
