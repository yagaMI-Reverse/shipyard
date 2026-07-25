variable "ingress_nginx_version" {
  description = "ingress-nginx chart version."
  type        = string
  default     = "4.11.3"
}

variable "metrics_server_version" {
  description = "metrics-server chart version."
  type        = string
  default     = "3.12.2"
}
