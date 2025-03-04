variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs where resources will be deployed"
  type        = list(string)
}

# Network ACL variables
variable "network_acl_enabled" {
  description = "Enable Network ACL for VPC"
  type        = bool
  default     = true
}

variable "network_acl_ingress_rules" {
  description = "List of ingress rules for Network ACL"
  type = list(object({
    rule_no    = number
    action     = string
    protocol   = string
    cidr_block = string
    from_port  = number
    to_port    = number
  }))
  default = [
    {
      rule_no    = 100
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "10.0.0.0/8"
      from_port  = 443
      to_port    = 443
    },
    {
      rule_no    = 110
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "10.0.0.0/8"
      from_port  = 80
      to_port    = 80
    },
    {
      rule_no    = 120
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "10.0.0.0/8"
      from_port  = 22
      to_port    = 22
    },
    {
      rule_no    = 130
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "10.0.0.0/8"
      from_port  = 1024
      to_port    = 65535
    }
  ]
}

variable "network_acl_egress_rules" {
  description = "List of egress rules for Network ACL"
  type = list(object({
    rule_no    = number
    action     = string
    protocol   = string
    cidr_block = string
    from_port  = number
    to_port    = number
  }))
  default = [
    {
      rule_no    = 100
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "0.0.0.0/0"
      from_port  = 443
      to_port    = 443
    },
    {
      rule_no    = 110
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "0.0.0.0/0"
      from_port  = 80
      to_port    = 80
    },
    {
      rule_no    = 120
      action     = "allow"
      protocol   = "tcp"
      cidr_block = "0.0.0.0/0"
      from_port  = 1024
      to_port    = 65535
    }
  ]
}

# VPC Flow Logs variables
variable "flow_logs_enabled" {
  description = "Enable VPC Flow Logs"
  type        = bool
  default     = true
}

variable "flow_logs_traffic_type" {
  description = "Type of traffic to capture in flow logs"
  type        = string
  default     = "ALL"
}

variable "flow_logs_retention" {
  description = "Number of days to retain flow logs in CloudWatch"
  type        = number
  default     = 90
}

variable "flow_logs_cloudwatch_log_group_name" {
  description = "CloudWatch log group name for VPC flow logs"
  type        = string
  default     = "vpc-flow-logs"
}

# Security Group variables
variable "create_security_group" {
  description = "Create a security group"
  type        = bool
  default     = true
}

variable "security_group_name" {
  description = "Name of the security group"
  type        = string
  default     = "restricted-sg"
}

variable "security_group_description" {
  description = "Description of the security group"
  type        = string
  default     = "Security group with least privilege access"
}

variable "security_group_ingress_rules" {
  description = "List of ingress rules for the security group"
  type = list(object({
    description     = string
    from_port       = number
    to_port         = number
    protocol        = string
    cidr_blocks     = list(string)
    security_groups = optional(list(string), [])
  }))
  default = []
}

variable "security_group_egress_rules" {
  description = "List of egress rules for the security group"
  type = list(object({
    description     = string
    from_port       = number
    to_port         = number
    protocol        = string
    cidr_blocks     = list(string)
    security_groups = optional(list(string), [])
  }))
  default = [
    {
      description = "Allow HTTPS outbound traffic"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  ]
}

# Encryption variables
variable "enable_s3_encryption" {
  description = "Enable server-side encryption for S3 bucket"
  type        = bool
  default     = true
}

variable "s3_encryption_algorithm" {
  description = "Server-side encryption algorithm to use"
  type        = string
  default     = "AES256"
}

variable "kms_key_id" {
  description = "ARN of KMS key to use for encryption (if using KMS)"
  type        = string
  default     = null
}

# VPC Endpoint variables
variable "vpc_endpoint_s3_enabled" {
  description = "Create S3 VPC endpoint"
  type        = bool
  default     = true
}

variable "vpc_endpoint_dynamodb_enabled" {
  description = "Create DynamoDB VPC endpoint"
  type        = bool
  default     = false
}

variable "vpc_endpoint_private_dns_enabled" {
  description = "Enable private DNS for VPC endpoints"
  type        = bool
  default     = true
}

variable "s3_endpoint_policy" {
  description = "Policy to attach to the S3 VPC endpoint"
  type        = string
  default     = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Effect": "Allow",
      "Resource": "*",
      "Principal": "*"
    }
  ]
}
POLICY
}

variable "dynamodb_endpoint_policy" {
  description = "Policy to attach to the DynamoDB VPC endpoint"
  type        = string
  default     = null
}

variable "enable_vpc_flow_logs_encryption" {
  description = "Enable encryption for VPC flow logs"
  type        = bool
  default     = true
}

variable "tags" {
  description = "A map of tags to add to all resources"
  type        = map(string)
  default     = {}
}