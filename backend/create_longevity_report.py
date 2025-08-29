#!/usr/bin/env python3
import json

with open('longevity_complete_1756426072.json', 'r') as f:
    data = json.load(f)

# Create markdown report
report = []
report.append('# COMPREHENSIVE LONGEVITY SUPPLEMENT BRANDS TEST REPORT')
report.append('')
report.append('## Test Configuration')
report.append(f"- **Prompt**: '{data['prompt']}'" )
report.append(f"- **Timestamp**: {data['timestamp']}")
report.append(f"- **Total Tests**: {len(data['tests'])}")
report.append('')
report.append('---')

for test in data['tests']:
    report.append('')
    report.append(f"## {test['test_name']}")
    report.append('')
    report.append('### Configuration')
    report.append(f"- **Vendor**: {test['vendor']}")
    report.append(f"- **Model**: {test['model']}")
    report.append(f"- **Grounded**: {test['grounded']}")
    report.append(f"- **Vantage Policy**: {test['vantage_policy']}")
    report.append(f"- **Country**: {test['country']}")
    report.append(f"- **Success**: {test['success']}")
    if test['success']:
        report.append(f"- **Latency**: {test['latency_ms']}ms")
        report.append(f"- **Grounded Effective**: {test.get('grounded_effective', False)}")
        report.append(f"- **Web Grounded**: {test.get('web_grounded', False)}")
        report.append(f"- **Tool Call Count**: {test.get('tool_call_count', 0)}")
    report.append('')
    report.append('### Usage')
    if test.get('usage'):
        usage = test['usage']
        if 'input_tokens' in usage:
            report.append(f"- **Input Tokens**: {usage.get('input_tokens', 'N/A')}")
            report.append(f"- **Output Tokens**: {usage.get('output_tokens', 'N/A')}")
        else:
            report.append(f"- **Prompt Tokens**: {usage.get('prompt_tokens', 'N/A')}")
            report.append(f"- **Completion Tokens**: {usage.get('completion_tokens', 'N/A')}")
        report.append(f"- **Total Tokens**: {usage.get('total_tokens', 'N/A')}")
    report.append('')
    report.append('### Full Response')
    report.append('```')
    if test['success']:
        response = test.get('full_response', '')
        if response:
            report.append(response)
        else:
            report.append('[Empty response - likely hit token limit or safety filter]')
    else:
        report.append(f"ERROR: {test.get('error', 'Unknown error')}")
    report.append('```')
    report.append('')
    report.append('---')

with open('LONGEVITY_COMPLETE_REPORT.md', 'w') as f:
    f.write('\n'.join(report))

print('Report saved to LONGEVITY_COMPLETE_REPORT.md')
print(f'Total size: {len("\n".join(report))} characters')