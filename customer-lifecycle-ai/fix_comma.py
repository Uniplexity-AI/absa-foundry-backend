with open(r'..\..\absa-foundry-frontend\src\views\Modules\datapipeline\EtlPipeline.vue', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace('}),,', '}),')

with open(r'..\..\absa-foundry-frontend\src\views\Modules\datapipeline\EtlPipeline.vue', 'w', encoding='utf-8') as f:
    f.write(code)
