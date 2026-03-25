output "cluster_name" {
  description = "EKS Cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS Cluster API endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  value       = aws_ecr_repository.app.repository_url
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}