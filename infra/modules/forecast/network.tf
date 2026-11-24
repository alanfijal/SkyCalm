resource "aws_vpc" "grid" {
  cidr_block           = "10.72.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${local.name}-grid" }
}
resource "aws_subnet" "grid" {
  vpc_id                  = aws_vpc.grid.id
  cidr_block              = "10.72.0.0/27"
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-grid" }
}
resource "aws_internet_gateway" "grid" { vpc_id = aws_vpc.grid.id }
resource "aws_route_table" "grid" {
  vpc_id = aws_vpc.grid.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.grid.id
  }
}
resource "aws_route_table_association" "grid" {
  subnet_id      = aws_subnet.grid.id
  route_table_id = aws_route_table.grid.id
}
resource "aws_vpc_endpoint" "regional" {
  for_each          = toset(["s3", "dynamodb"])
  vpc_id            = aws_vpc.grid.id
  service_name      = "com.amazonaws.${local.region}.${each.key}"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.grid.id]
}
resource "aws_security_group" "grid" {
  name        = "${local.name}-grid"
  description = "HTTPS egress for regional services and public NOAA ranges"
  vpc_id      = aws_vpc.grid.id
}
# NOAA's public US S3 endpoint is outside the Stockholm gateway endpoint. Its IPs rotate.
#trivy:ignore:AVD-AWS-0104
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.grid.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}
