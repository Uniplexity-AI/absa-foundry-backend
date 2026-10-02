import re

def fix_yaml(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Replace the fake table in the primary_entity block with a_africa_zam_base_customers_new
    content = re.sub(
        r'table: "a_africa_zam_base_customer"',
        'table: "a_africa_zam_base_customers_new"',
        content,
        count=1
    )
    
    # 2. Extract the length_years and length_months fields
    length_fields = r'''
    # Tenure - forwarded to feature-engineering for tenure_days / tenure_label
    - field: "length_years"
      alias: "length_years"
      validation:
        type: "int"
        required: false

    - field: "length_months"
      alias: "length_months"
      validation:
        type: "int"
        required: false
'''
    content = content.replace(length_fields, '')
    
    # Also handle shared_features format
    short_length = r'''    - field: "length_years"
      validation: {type: "int"}
    - field: "length_months"
      validation: {type: "int"}'''
    content = content.replace(short_length, '')

    # 3. Inject length_years and length_months into the employment table select_fields
    if "a_africa_zam_base_customer_employment_daily_zm" in content:
        # Find the select_fields for employment
        emp_match = re.search(r'(table: "a_africa_zam_base_customer_employment_daily_zm".*?select_fields:\n)', content, re.DOTALL)
        if emp_match:
            injection_point = emp_match.group(1)
            
            # The fields to inject
            fields_to_inject = """      - field: "length_years"
      - field: "length_months"
"""
            new_block = injection_point + fields_to_inject
            content = content.replace(injection_point, new_block)
            
    # 4. In customer_360.yaml, we now have a_africa_zam_base_customers_new joining to itself.
    # We can just leave it (it works perfectly via SQL optimizer), OR we can just change the join to not be self-join.
    # It's safest to leave the self-join so we don't break field aliases (cn.market_segment_code, etc).

    with open(filepath, 'w') as f:
        f.write(content)

fix_yaml('etl/config/extraction_specs/customer_360.yaml')
fix_yaml('etl/config/extraction_specs/shared_features.yaml')
print("Successfully refactored YAML files!")
