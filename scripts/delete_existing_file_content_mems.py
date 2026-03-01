from core.store_provider import get_store
store = get_store()
mems = store.collection.search().where("type = 'file_content' AND repo = 'devmemoryindex'").limit(10000).to_list()
y = 0
for m in mems:
    store.delete(m['id'])
    y += 1
    print(f'Deleted {y} file_content memories', end='\r')
print(f'Cleared {y} file_content memories')