import yaml

with open('customer-lifecycle-ai/etl/config/extraction_specs/customer_360.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Remove default: UNKNOWN from gender
for field in config.get('primary_entity', {}).get('select_fields', []):
    if field.get('alias') == 'gender':
        if 'default' in field.get('validation', {}):
            del field['validation']['default']

# Remove default_value: UNKNOWN from standardizations
for tf in config.get('transform', {}).get('standardization', []):
    if tf.get('field_name') == 'gender':
        if 'default_value' in tf:
            del tf['default_value']

# Update calculated fields
for cf in config.get('calculated_fields', []):
    if cf['name'] == 'full_name':
        cf['expression'] = "c.first_name || ' ' || c.family_name"
    elif cf['name'] == 'national_id':
        cf['expression'] = 'c.id_card_number'
    elif cf['name'] == 'customer_since_date':
        cf['expression'] = 'c.relationship_established'
    elif cf['name'] == 'kyc_tier':
        cf['expression'] = 'c.kyc_status'
    elif cf['name'] == 'account_number':
        cf['expression'] = 'sms.account_number'
    elif cf['name'] == 'date_of_birth':
        cf['expression'] = "'NULL'"
    elif cf['name'] == 'status':
        cf['expression'] = 'c.customer_status'
    elif cf['name'] == 'is_deleted':
        cf['expression'] = "'NULL'"

# Add join
sms_join = {
    'table': 'a_africa_zam_base_customer_sms',
    'alias': 'sms',
    'join_type': 'left',
    'on': [{'left': 'c.customer_number', 'right': 'sms.customer_number'}]
}
if 'joins' not in config:
    config['joins'] = []
config['joins'].append(sms_join)

with open('customer-lifecycle-ai/etl/config/extraction_specs/customer_360.yaml', 'w') as f:
    yaml.dump(config, f, sort_keys=False, default_flow_style=False)
