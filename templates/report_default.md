# PromptPressure Evaluation Report

**Date:** {{ timestamp }}
**Model:** {{ config.get('model_name') }} ({{ config.get('adapter') }})

## Summary stats
- **Total Prompts:** {{ total_evals }}
{% if metrics.get('average_response_time') %}- **Avg Latency:** {{ "%.2f"|format(metrics['average_response_time']) }}s {% endif %}
{% if metrics.get('errors') %}- **Errors:** {{ metrics['errors'] }}{% endif %}

## Detailed Results

| ID | Prompt | Response Snippet | Scores |
|----|--------|------------------|--------|
{% for item in results %}
| {{ item.get('id', '-') }} | {{ item.get('prompt')[:50] | replace('\n', ' ') }}... | {{ item.get('response')[:50] | replace('\n', ' ') }}... | {% if item.get('scores') %}{% for k, v in item.get('scores').items() %}{{ k }}:{{ '✅' if v else '❌' }} {% endfor %}{% else %} - {% endif %} |
{% endfor %}
