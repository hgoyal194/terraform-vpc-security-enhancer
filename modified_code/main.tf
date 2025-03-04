provider "aws" {
  region = local.region
}

data "aws_availability_zones" "available" {}

locals {
  name   = "ex-${basename(path.cwd)}"
  region = "eu-west-1"

  vpc_cidr = "10.0.0.0/16"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = {
    Example    = local.name
    GithubRepo = "terraform-aws-vpc"
    GithubOrg  = "terraform-aws-modules"
  }
}

################################################################################
# VPC Module
################################################################################

module "vpc" {
  source = "../../"

  name = local.name
  cidr = local.vpc_cidr

  azs                 = local.azs
  private_subnets     = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k)]
  public_subnets      = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 4)]
  database_subnets    = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 8)]
  elasticache_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 12)]
  redshift_subnets    = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 16)]
  intra_subnets       = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 20)]

  private_subnet_names = ["Private Subnet One", "Private Subnet Two"]
  # public_subnet_names omitted to show default name generation for all three subnets
  database_subnet_names    = ["DB Subnet One"]
  elasticache_subnet_names = ["Elasticache Subnet One", "Elasticache Subnet Two"]
  redshift_subnet_names    = ["Redshift Subnet One", "Redshift Subnet Two", "Redshift Subnet Three"]
  intra_subnet_names       = []

  # Enable dedicated network ACLs for each subnet
  public_dedicated_network_acl    = true
  private_dedicated_network_acl   = true
  database_dedicated_network_acl  = true
  elasticache_dedicated_network_acl = true
  redshift_dedicated_network_acl  = true
  intra_dedicated_network_acl     = true

  # Strict public subnet ACL rules
  public_inbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"
    },
    {
      rule_number = 110
      rule_action = "allow"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"
    },
    {
      rule_number = 120
      rule_action = "allow"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_block  = "10.0.0.0/8"  # Restrict SSH access to VPC CIDR
    },
    {
      rule_number = 130
      rule_action = "allow"
      from_port   = 1024
      to_port     = 65535
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"  # Allow ephemeral ports
    }
  ]
  
  public_outbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"
    },
    {
      rule_number = 110
      rule_action = "allow"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"
    },
    {
      rule_number = 120
      rule_action = "allow"
      from_port   = 1024
      to_port     = 65535
      protocol    = "tcp"
      cidr_block  = "0.0.0.0/0"
    }
  ]

  # Secure private subnet ACL rules
  private_inbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_block  = local.vpc_cidr  # Only allow traffic from within VPC
    }
  ]
  
  private_outbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_block  = "0.0.0.0/0"
    }
  ]

  # Secure database subnet ACL rules
  database_inbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 5432  # PostgreSQL
      to_port     = 5432
      protocol    = "tcp"
      cidr_block  = local.vpc_cidr
    },
    {
      rule_number = 110
      rule_action = "allow"
      from_port   = 3306  # MySQL
      to_port     = 3306
      protocol    = "tcp"
      cidr_block  = local.vpc_cidr
    },
    {
      rule_number = 120
      rule_action = "allow"
      from_port   = 1433  # MSSQL
      to_port     = 1433
      protocol    = "tcp"
      cidr_block  = local.vpc_cidr
    }
  ]
  
  database_outbound_acl_rules = [
    {
      rule_number = 100
      rule_action = "allow"
      from_port   = 1024
      to_port     = 65535
      protocol    = "tcp"
      cidr_block  = local.vpc_cidr
    }
  ]

  create_database_subnet_group  = false
  manage_default_network_acl    = true
  manage_default_route_table    = true
  manage_default_security_group = true

  # Enhance the default security group with least privilege
  default_security_group_ingress = [
    {
      description = "Allow internal traffic only"
      self        = true
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
    }
  ]
  
  default_security_group_egress = [
    {
      description = "Allow outbound HTTPS only"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = "0.0.0.0/0"
    }
  ]

  enable_dns_hostnames = true
  enable_dns_support   = true

  enable_nat_gateway = true
  single_nat_gateway = true

  customer_gateways = {
    IP1 = {
      bgp_asn     = 65112
      ip_address  = "1.2.3.4"
      device_name = "some_name"
    },
    IP2 = {
      bgp_asn    = 65112
      ip_address = "5.6.7.8"
    }
  }

  enable_vpn_gateway = true

  enable_dhcp_options              = true
  dhcp_options_domain_name         = "service.consul"
  dhcp_options_domain_name_servers = ["127.0.0.1", "10.10.0.2"]

  # Enhanced VPC Flow Logs with CloudWatch integration
  vpc_flow_log_iam_role_name            = "vpc-complete-example-role"
  vpc_flow_log_iam_role_use_name_prefix = false
  enable_flow_log                       = true
  create_flow_log_cloudwatch_log_group  = true
  create_flow_log_cloudwatch_iam_role   = true
  flow_log_max_aggregation_interval     = 60
  flow_log_cloudwatch_log_group_retention_in_days = 90
  flow_log_cloudwatch_log_group_kms_key_id = null # Add your KMS key ARN here for log encryption
  flow_log_traffic_type                 = "ALL"
  flow_log_destination_type             = "cloud-watch-logs"
  flow_log_log_format                   = "$${version} $${account-id} $${interface-id} $${srcaddr} $${dstaddr} $${srcport} $${dstport} $${protocol} $${packets} $${bytes} $${start} $${end} $${action} $${log-status} $${vpc-id} $${subnet-id} $${instance-id} $${tcp-flags} $${type} $${pkt-srcaddr} $${pkt-dstaddr} $${region} $${az-id} $${sublocation-type} $${sublocation-id}"

  tags = local.tags
}

################################################################################
# VPC Endpoints Module
################################################################################

module "vpc_endpoints" {
  source = "../../modules/vpc-endpoints"

  vpc_id = module.vpc.vpc_id

  create_security_group      = true
  security_group_name_prefix = "${local.name}-vpc-endpoints-"
  security_group_description = "VPC endpoint security group"
  security_group_rules = {
    ingress_https = {
      description = "HTTPS from VPC"
      cidr_blocks = [module.vpc.vpc_cidr_block]
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
    },
    egress_https = {
      description = "Allow all outbound HTTPS traffic"
      type        = "egress"
      cidr_blocks = ["0.0.0.0/0"]
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
    }
  }

  endpoints = {
    s3 = {
      service             = "s3"
      private_dns_enabled = true
      dns_options = {
        private_dns_only_for_inbound_resolver_endpoint = false
      }
      tags = { Name = "s3-vpc-endpoint" }
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Sid = "RestrictBucketAccessToVPC",
            Effect = "Allow",
            Principal = "*",
            Action = [
              "s3:GetObject",
              "s3:ListBucket",
              "s3:PutObject"
            ],
            Resource = ["*"],
            Condition = {
              StringEquals = {
                "aws:sourceVpc": module.vpc.vpc_id
              }
            }
          }
        ]
      })
    },
    dynamodb = {
      service         = "dynamodb"
      service_type    = "Gateway"
      route_table_ids = flatten([module.vpc.intra_route_table_ids, module.vpc.private_route_table_ids, module.vpc.public_route_table_ids])
      policy          = data.aws_iam_policy_document.dynamodb_endpoint_policy.json
      tags            = { Name = "dynamodb-vpc-endpoint" }
    },
    ecs = {
      service             = "ecs"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy = data.aws_iam_policy_document.generic_endpoint_policy.json
    },
    ecs_telemetry = {
      create              = false
      service             = "ecs-telemetry"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
    },
    ecr_api = {
      service             = "ecr.api"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy              = data.aws_iam_policy_document.generic_endpoint_policy.json
    },
    ecr_dkr = {
      service             = "ecr.dkr"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy              = data.aws_iam_policy_document.generic_endpoint_policy.json
    },
    rds = {
      service             = "rds"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.rds.id]
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Sid = "RestrictRDSEndpointAccess",
            Effect = "Allow",
            Principal = "*",
            Action = [
              "rds:*"
            ],
            Resource = "*",
            Condition = {
              StringEquals = {
                "aws:sourceVpc": module.vpc.vpc_id
              }
            }
          }
        ]
      })
    },
    ssm = {
      service             = "ssm"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy              = data.aws_iam_policy_document.generic_endpoint_policy.json
    },
    secretsmanager = {
      service             = "secretsmanager"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy              = data.aws_iam_policy_document.generic_endpoint_policy.json
    },
    kms = {
      service             = "kms"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      policy              = data.aws_iam_policy_document.generic_endpoint_policy.json
    }
  }

  tags = merge(local.tags, {
    Project  = "Secret"
    Endpoint = "true"
  })
}

module "vpc_endpoints_nocreate" {
  source = "../../modules/vpc-endpoints"

  create = false
}

################################################################################
# Supporting Resources
################################################################################

data "aws_iam_policy_document" "dynamodb_endpoint_policy" {
  statement {
    effect    = "Deny"
    actions   = ["dynamodb:*"]
    resources = ["*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:sourceVpc"

      values = [module.vpc.vpc_id]
    }
  }
}

data "aws_iam_policy_document" "generic_endpoint_policy" {
  statement {
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:SourceVpc"

      values = [module.vpc.vpc_id]
    }
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.name}-rds"
  description = "Allow PostgreSQL inbound traffic"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}