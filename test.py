import requests

cookies = {
    'loginAppkey': '21226717',
    # '_ati': '1570860693343',
    # 'gyTenant': '84660043531',
    # 'device_id': 'EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLE',
    # 'route': 'c3f21301cc80a84c3f63260a9cf3a701',
    'userId': '976938821241',
    # 'pin': '55f73723eedcce7778664e3c2b3db0ec',
    'shiroCookie': '2167a8a6-c43a-4a35-8a6c-b380563f5745',
    # '3AB9D23F7A4B3CSS': 'jdd03EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLEAAAAM6IL5LCYQAAAAADN6PGGYNW2562AX',
    # 'secToken': '7EFnNzm7PKvtC0fSZbZ4KiejJ085rCv383RoIOBo8TQvVYN7qItUtG9HnZIDeWv7CPx%2BB8sEvuYEh17KRLSOGtna%2FwWi46cmLrlWXIJo1la4TSRDfXQGr5rP7AzxKs8yfzxhtzEpZrOvbHdQAjXyhQ%3D%3D',
    # '3AB9D23F7A4B3C9B': 'EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLE',
    # 'cid': '1779240193012_9c7dc14f51edbdce13716f88fe1cd4d5',
    # 'acw_tc': '276077e017792429189538393e9013d993176bf8376fde495ccb2d011cf7ba',
    # 'tfstk': 'gixrqF0MUMAXYrGMQdjE7v46WqjJNMl_rH1CKpvhF_fldwY4TdOFR8TSewvhgBC5PgfCTIJ9dYKIegXh-BOMPbI5R9reLEHROM_BTyA1qwL5O_1FYpdZhfisfLpRvwGs1cONTULdbuX3Owfc296e0IREfLp8nLSHzhns83Qi69fHtafcm950ZTfktZqcpsqlKuX3ixWdiMqlEa20oOWaxy4ktKDVpsfhxaAhmxWdi6jhxXeduNoVIaD5FPI5K8iqH1JlgkqHqDQd_jWFHwKVKaJCPrEgjvBPz1vlgb8wdAbeaa-j45ByodR5UBnT2gberFjkYfoPmdLXZtRn_y5D73KF53laW_xR9CSkujqPxixy5NIE78BX4KxO83hzm_RvnFsJjjEesK962ZKE_SfpPOIcUEk3o_bh4SVdnGO6vUP3-aXA31Mq3Co4JRCg8yR4JyQDOt5seLULJabf31MqRyUdoMBV1YC5.',
}

headers = {
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://v2.guanyierp.com',
    'Referer': 'https://v2.guanyierp.com/tc/trade/trade_order_approve',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
    'bx-v': '2.5.11',
    'doudian-event-id': '1779242919000875',
    'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    # 'Cookie': 'loginAppkey=21226717; _ati=1570860693343; gyTenant=84660043531; device_id=EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLE; route=c3f21301cc80a84c3f63260a9cf3a701; userId=976938821241; pin=55f73723eedcce7778664e3c2b3db0ec; shiroCookie=22b2f97f-f971-488d-aa89-ca2d803f7d25; 3AB9D23F7A4B3CSS=jdd03EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLEAAAAM6IL5LCYQAAAAADN6PGGYNW2562AX; secToken=7EFnNzm7PKvtC0fSZbZ4KiejJ085rCv383RoIOBo8TQvVYN7qItUtG9HnZIDeWv7CPx%2BB8sEvuYEh17KRLSOGtna%2FwWi46cmLrlWXIJo1la4TSRDfXQGr5rP7AzxKs8yfzxhtzEpZrOvbHdQAjXyhQ%3D%3D; 3AB9D23F7A4B3C9B=EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72ADHCIPSMWW42AYLYHTCGFYW4PLE; cid=1779240193012_9c7dc14f51edbdce13716f88fe1cd4d5; acw_tc=276077e017792429189538393e9013d993176bf8376fde495ccb2d011cf7ba; tfstk=gixrqF0MUMAXYrGMQdjE7v46WqjJNMl_rH1CKpvhF_fldwY4TdOFR8TSewvhgBC5PgfCTIJ9dYKIegXh-BOMPbI5R9reLEHROM_BTyA1qwL5O_1FYpdZhfisfLpRvwGs1cONTULdbuX3Owfc296e0IREfLp8nLSHzhns83Qi69fHtafcm950ZTfktZqcpsqlKuX3ixWdiMqlEa20oOWaxy4ktKDVpsfhxaAhmxWdi6jhxXeduNoVIaD5FPI5K8iqH1JlgkqHqDQd_jWFHwKVKaJCPrEgjvBPz1vlgb8wdAbeaa-j45ByodR5UBnT2gberFjkYfoPmdLXZtRn_y5D73KF53laW_xR9CSkujqPxixy5NIE78BX4KxO83hzm_RvnFsJjjEesK962ZKE_SfpPOIcUEk3o_bh4SVdnGO6vUP3-aXA31Mq3Co4JRCg8yR4JyQDOt5seLULJabf31MqRyUdoMBV1YC5.',
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
    cookies=cookies,
    headers=headers,
    data=data,
)
print(response.json())