import yaml

yaml_path = 'etl/config/extraction_specs/accounts.yaml'

with open(yaml_path, 'r') as f:
    config = yaml.safe_load(f)

for item in config['transform']['standardization']:
    if item['field_name'] == 'account_type':
        item['mappings'] = {
            '0': 'Ultimate_Plus_Account', '1': 'Ordinary Loan', '2': 'Mortgage Loan', '3': 'Staff Current',
            '4': 'Staff Loan', '5': 'Personal Loan', '6': 'Invoice Discounting', '7': 'Trade Loan Facility',
            '8': 'Call Deposit', '9': 'Import LC Refinancing', '10': 'Fixed Deposit', '11': 'VAF Loans',
            '12': 'Control Accounts', '14': 'Memorandum', '15': 'Prepaid Cards', '16': 'Profit And Loss',
            '20': 'Premier CFC Current Account', '21': 'Premier Life CFC Current Account', '22': 'Premier Fixed Deposit',
            '23': 'Premier Life Fixed Deposit', '24': 'Premier Home Loan', '25': 'Premier Life Home Loan',
            '26': 'BarclayloanDirect', '27': 'USD_Barclayloan', '28': 'Barclayloan Plus (Variable Rate)',
            '29': 'Scheme Loan Plus', '30': 'Premier Life Loan Plus (Variable Rate)', '31': 'Barclayloan',
            '32': 'Staff Barclayloan', '33': 'Treasury Deposits A/C', '34': 'CFC Personal Current',
            '35': 'CFC Business Current A/C', '36': 'CFC Business Loan Account', '37': 'CFC Fixed Deposit Account',
            '38': 'Executive Loan Account', '39': 'Local Business CFC', '40': 'Business Premium',
            '41': 'Business Current Account', '42': 'Business Fixed Deposits', '45': 'Local Business Current Account',
            '49': 'Ultimate Account', '50': 'Local Business Gold', '51': 'Higher Rate Dep', '52': 'Junior Mega Savings',
            '53': 'Ignition Account', '54': 'LA RIBA Current Account', '55': 'Test Accounts', '59': 'CFC SME Loan Account',
            '60': 'CFC SME Current Account', '61': 'Business Solution Loan', '62': 'Community Account',
            '63': 'CDA - Large Corporate', '64': 'Business Current (Transactions)', '65': 'Business Current (Trans & Cash)',
            '66': 'Local Buss Bonus Savings', '67': 'Scheme Loan', '68': 'Business Current Account',
            '69': 'Business Savings', '70': 'Bank Account', '71': 'Bonus Savings', '72': 'Instant Savings Account',
            '73': 'Prestige Current', '74': 'High Rate Savings', '75': 'Prestige Plus', '76': 'High Interest Bonus',
            '77': 'Prestige Bonus Savings', '78': 'Prestige Loan', '79': 'Premier_Plus_Account', '80': 'Potential Loss',
            '81': 'Control Accounts', '82': 'Financial Accounts', '83': 'Nostro Accounts', '84': 'Liability',
            '85': 'Head Office', '86': 'Reconcilable', '87': 'Premier Bonus Savings', '88': 'Premier Loan',
            '89': 'Premier Account', '91': 'NGO Account', '93': 'Tonse Bank Account', '94': 'Tonse Savings Account',
            '95': 'GRZ Account', '96': 'Financial Institutions', '97': 'Staff Study Loan', '98': 'Staff Personal Loan',
            '99': 'Staff House Loan'
        }

# Add branch_code standardization
branch_mapping = {
    'field_name': 'branch_code',
    'mappings': {
        '1': 'Head Office', '2': 'Head Office - Elunda', '3': 'Chingola & Chingola Prestige',
        '4': 'Chipata', '5': 'Choma', '6': 'Kabwe', '7': 'Kafue', '8': 'Lusaka - Mungwi Branch',
        '9': 'Kitwe Business Centre', '10': 'Kitwe Chimwemwe', '11': 'Kapiri Mposhi',
        '12': 'Livingstone & Livingstone Prestige', '13': 'Luanshya', '14': 'Lusaka Northend',
        '15': 'Lusaka Levy Branch', '16': 'Lusaka Business Centre', '17': 'Lusaka Longacres & Prestige',
        '18': 'Kasumbalesa', '19': 'Lusaka - Industrial', '20': 'Mansa', '21': 'Mazabuka', '22': 'Mfuwe',
        '23': 'Mufulira', '24': 'Monze', '25': 'Ndola Business Centre', '26': 'East Park Mall',
        '27': 'Kalumbila', '29': 'Solwezi', '30': 'Petauke', '31': 'Lundazi', '32': 'Kasama',
        '33': 'Centro Mall Branch', '34': 'Absa House Premier', '35': 'Mongu', '36': 'Garden City',
        '37': 'Chongwe', '38': 'Mkushi', '39': 'Ndola Operations Processing Centre', '40': 'Nakonde',
        '41': 'Mukuba Branch', '42': 'Chirundu', '43': 'Kabwata', '44': 'Lusaka - Chawama',
        '45': 'Mpika', '46': 'Ndola - Masala', '47': 'Chambishi', '48': 'Mpongwe',
        '49': 'East Park Mall', '50': 'Lusaka Operations Processing Centre',
        '51': 'Cosmopolitan Branch', '52': 'Kitwe Operations Processing Centre', '53': 'Chililabombwe',
        '54': 'Lusaka Kabulenga', '55': 'Nkwazi Premium Banking Centre', '56': 'Islamic Banking'
    },
    'default_value': 'UNKNOWN'
}

# Ensure it's not added twice
existing = [x['field_name'] for x in config['transform']['standardization']]
if 'branch_code' not in existing:
    config['transform']['standardization'].append(branch_mapping)

class MyDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)

with open(yaml_path, 'w') as f:
    yaml.dump(config, f, Dumper=MyDumper, default_flow_style=False, sort_keys=False)
print('Updated YAML mappings')
