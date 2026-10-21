# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

# --- Amazon ECR
resource "aws_ecr_repository" "app" {
  name                 = "mon-app"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Amazon S3
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- AWS Lambda
data "archive_file" "function_placeholder" {
  type        = "zip"
  output_path = "${path.module}/function-placeholder.zip"

  source {
    content  = "def handler(event, context):\n    return {\"statusCode\": 200, \"body\": \"Code à déployer par la CI\"}\n"
    filename = "main.py"
  }
}

resource "aws_iam_role" "function" {
  name = "mon-app-function"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "function_logs" {
  role       = aws_iam_role.function.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "fn_staging" {
  function_name    = "mon-app-staging"
  role             = aws_iam_role.function.arn
  runtime          = "python3.13"
  handler          = "main.handler"
  memory_size      = 256
  timeout          = 30
  filename         = data.archive_file.function_placeholder.output_path
  source_code_hash = data.archive_file.function_placeholder.output_base64sha256

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_function_url" "fn_staging" {
  function_name      = aws_lambda_function.fn_staging.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "fn_staging_url" {
  statement_id           = "AllowPublicUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.fn_staging.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "fn_staging_invoke" {
  statement_id             = "AllowPublicInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.fn_staging.function_name
  principal                = "*"
  invoked_via_function_url = true
}

resource "aws_lambda_function" "fn_production" {
  function_name    = "mon-app"
  role             = aws_iam_role.function.arn
  runtime          = "python3.13"
  handler          = "main.handler"
  memory_size      = 256
  timeout          = 30
  filename         = data.archive_file.function_placeholder.output_path
  source_code_hash = data.archive_file.function_placeholder.output_base64sha256

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_function_url" "fn_production" {
  function_name      = aws_lambda_function.fn_production.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "fn_production_url" {
  statement_id           = "AllowPublicUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.fn_production.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "fn_production_invoke" {
  statement_id             = "AllowPublicInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.fn_production.function_name
  principal                = "*"
  invoked_via_function_url = true
}
