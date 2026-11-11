"""Convert a db-query results.json into one CSV per statement. Usage: tocsv.py results.json prefix label1,label2,..."""
import csv, json, sys
path, prefix, labels = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
d = json.load(open(path))
res = d['results']
assert len(res) == len(labels), (len(res), labels)
for s, lab in zip(res, labels):
    out = f'{prefix}_{lab}.csv'
    with open(out, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(s['columns']); w.writerows(s['rows'])
    print(lab, s['status'], 'rows', s['row_count'], 'truncated', s['truncated'], 'cols', s['columns'])
