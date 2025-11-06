terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region
}

# IAM Role for Amplify
resource "aws_iam_role" "amplify" {
  name = "${var.project_name}-amplify-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "amplify.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-amplify-role"
  }
}

# IAM Policy for Amplify to access repository (if using GitHub)
resource "aws_iam_role_policy" "amplify_policy" {
  name = "${var.project_name}-amplify-policy"
  role = aws_iam_role.amplify.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Amplify App for Frontend
resource "aws_amplify_app" "frontend" {
  name       = "${var.project_name}-frontend"

  # GitHub連携の場合のみリポジトリを設定
  repository = var.github_repo_url != "" ? var.github_repo_url : null

  # GitHub連携の場合のアクセストークン
  access_token = var.github_access_token != "" ? var.github_access_token : null

  # Build settings - amplify.yamlを使用
  build_spec = file("${path.root}/../../amplify.yaml")

  # 環境変数
  environment_variables = {
    NEXT_PUBLIC_API_URL          = var.backend_api_url
    AMPLIFY_MONOREPO_APP_ROOT    = "frontend"
    _LIVE_UPDATES                = jsonencode([
      {
        pkg     = "next"
        type    = "npm"
        version = "latest"
      }
    ])
  }

  # カスタムルール（Next.js用）
  custom_rule {
    source = "/<*>"
    status = "404-200"
    target = "/index.html"
  }

  custom_rule {
    source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>"
    status = "200"
    target = "/index.html"
  }

  # カスタムヘッダーはNext.js config (next.config.js)で管理されます
  # Amplifyのmonorepo構造との互換性のため

  # プラットフォーム設定
  platform = "WEB_COMPUTE"

  iam_service_role_arn = aws_iam_role.amplify.arn

  tags = {
    Name        = "${var.project_name}-frontend"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Amplify Branch (main)
resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.frontend.id
  branch_name = var.branch_name

  enable_auto_build = var.enable_auto_build

  framework = "Next.js - SSR"
  stage     = var.environment == "production" ? "PRODUCTION" : "DEVELOPMENT"

  environment_variables = {
    NEXT_PUBLIC_API_URL          = var.backend_api_url
    AMPLIFY_MONOREPO_APP_ROOT    = "frontend"
  }

  tags = {
    Name        = "${var.project_name}-${var.branch_name}-branch"
    Environment = var.environment
  }
}

# カスタムドメイン（オプション）
resource "aws_amplify_domain_association" "custom_domain" {
  count = var.custom_domain != "" ? 1 : 0

  app_id      = aws_amplify_app.frontend.id
  domain_name = var.custom_domain

  sub_domain {
    branch_name = aws_amplify_branch.main.branch_name
    prefix      = var.subdomain_prefix
  }

  # wwwサブドメインも追加（オプション）
  dynamic "sub_domain" {
    for_each = var.enable_www_redirect ? [1] : []
    content {
      branch_name = aws_amplify_branch.main.branch_name
      prefix      = "www"
    }
  }
}
