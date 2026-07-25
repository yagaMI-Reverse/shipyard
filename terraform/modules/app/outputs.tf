output "release_name" {
  description = "Installed Helm release."
  value       = helm_release.docuchat.name
}

output "namespace" {
  description = "Namespace the release lives in."
  value       = helm_release.docuchat.namespace
}

output "chart_version" {
  description = "Chart version that was deployed."
  value       = helm_release.docuchat.version
}
