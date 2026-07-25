{{/*
Chart-wide naming and label helpers.
*/}}

{{- define "docuchat.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "docuchat.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "docuchat.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Labels shared by every object in the release. */}}
{{- define "docuchat.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "docuchat.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: docuchat
{{- end -}}

{{/* Selector labels for a component: {{ include "docuchat.selectorLabels" (dict "ctx" . "component" "api") }} */}}
{{- define "docuchat.selectorLabels" -}}
app.kubernetes.io/name: {{ include "docuchat.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "docuchat.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "docuchat.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Postgres Service DNS name and the DSN the API connects with. */}}
{{- define "docuchat.postgresHost" -}}
{{- printf "%s-postgres" (include "docuchat.fullname" .) -}}
{{- end -}}

{{- define "docuchat.databaseUrl" -}}
{{- if .Values.postgres.enabled -}}
{{- printf "postgresql://%s:%s@%s:5432/%s" .Values.postgres.auth.username .Values.postgres.auth.password (include "docuchat.postgresHost" .) .Values.postgres.auth.database -}}
{{- else -}}
{{- .Values.api.externalDatabaseUrl | default "" -}}
{{- end -}}
{{- end -}}
