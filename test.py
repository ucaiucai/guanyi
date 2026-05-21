import requests

cookies = {
    'loginAppkey': '21226717',
    'userId': '976938821241',
    'shiroCookie': '619985c4-58a3-4aa5-bb25-8b161a75c54a',
   }

headers = {
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    "Cookie": "loginAppkey=21226717;userId=976938821241;shiroCookie=bc76aab7-f7df-4db0-94ef-e1642a7c39ed"
}

data = {
    'page': '1',
    'limit': '50',
    'start': '0',
    'shopIds': '354109126320',
    'cod': '',
    'chkMemo': 'false',
    'hasInvoice': '',
    'refund': '',
    'financeReject': '',
}

response = requests.post(
    'https://v2.guanyierp.com/tc/trade/trade_order_approve/data/list',
    headers=headers,
    data=data,
)
print(response.json())