import re
from base64 import b64decode
from asn1crypto import cms
from datetime import datetime
import polars as pl
from pathlib import Path
from time import time
TMP_DIR = Path('tmp')
TMP_DIR.mkdir(exist_ok=True)

def get_int(value):
    """
    Если value — это asn1crypto.core.Integer, возвращаем value.native (int).
    Если же value уже int — возвращаем его «как есть».
    """
    try:
        return value.native
    except AttributeError:
        return value

def load_cms_der_from_pem(path_to_pem_sig: str) -> bytes:
    """
    Читает файл с обёрткой PEM (BEGIN/END CMS), возвращает DER-байты.
    """
    with open(path_to_pem_sig, "r", encoding="utf-8") as f:
        data = f.read()

    pem_body = re.sub(r"-----BEGIN CMS-----", "", data)
    pem_body = re.sub(r"-----END CMS-----", "", pem_body)
    pem_body = re.sub(r"\s+", "", pem_body)

    der_bytes = b64decode(pem_body)
    return der_bytes

def format_signing_time(signer_info):
    """
    Пытается извлечь из signer_info атрибут 'signing_time' и вернуть строку 'дд.мм.гггг'.
    Если атрибута нет — возвращает None.
    """
    # Вместо signer_info.get('signed_attrs') надо взять signer_info['signed_attrs']
    try:
        signed_attrs = signer_info['signed_attrs']
    except KeyError:
        return None

    if signed_attrs is None:
        return None

    for attr in signed_attrs:
        if attr['type'].native == 'signing_time':
            value = attr['values'][0]
            dt: datetime = value.native
            return dt.strftime("%d.%m.%Y %H:%M:%S")
    return None

def parse_cms_signers(der_bytes: bytes, path_str: str) -> pl.DataFrame:
    path = Path(path_str)
    content_info = cms.ContentInfo.load(der_bytes)
    if content_info['content_type'].native != 'signed_data':
        raise ValueError("Ожидался тип 'signed_data', но получили: %r" %
                         content_info['content_type'].native)

    signed_data = content_info['content']

    # 1) Собираем сертификаты в мапу (issuer+serial → cert)
    cert_map = {}
    if signed_data['certificates'] is not None:
        for cert_choice in signed_data['certificates']:
            if cert_choice.name == 'certificate':
                cert = cert_choice.chosen  # это asn1crypto.x509.Certificate
                issuer = cert.issuer.native
                serial_obj = cert.serial_number
                serial = get_int(serial_obj)

                issuer_items = tuple(sorted(issuer.items()))
                key = (issuer_items, serial)
                cert_map[key] = cert

    # 2) Проходимся по каждому SignerInfo
    df = pl.DataFrame({
        'Папка': [],
        'Название документа': [],
        'Дата подписания': [],
        'Имя': [],
        'Организация': [],
        })
    for idx, signer in enumerate(signed_data['signer_infos'], 1):
        # print(f"=== Подписант #{idx} ===")

        # Сначала пытаемся получить дату подписи
        signing_date = format_signing_time(signer)
        if signing_date:
            # print("Дата подписания:", signing_date)
            pass
        else:
            print("Дата подписания: не найдена в signed_attrs")

        sid = signer['sid']

        # Вариант 1: IssuerAndSerialNumber
        if sid.name == 'issuer_and_serial_number':
            ias = sid.chosen
            issuer = ias['issuer'].native
            serial_obj = ias['serial_number']
            serial = get_int(serial_obj)

            issuer_items = tuple(sorted(issuer.items()))
            key = (issuer_items, serial)
            cert = cert_map.get(key)
            if cert:
                subject = cert.subject.native
                # print("Subject:", json.dumps(subject, ensure_ascii=False, indent=4))
                name = subject.get('surname') + " " + subject.get('given_name')
                organization = subject.get('common_name') if subject.get('locality_name') else ''
                path = path.absolute()
                folders = f'{path.parent.parent.parent.name}/{path.parent.parent.name}/{path.parent.name}'
                temp_df = pl.DataFrame({
                    'Папка': [folders],
                    'Название документа': [path.name],
                    'Дата подписания': [signing_date],
                    'Имя': [name],
                    'Организация': [organization],
                })
                # print(temp_df)
                if df.is_empty():
                    df = temp_df
                else:
                    df.vstack(temp_df, in_place=True)
            else:
                print("Сертификат подписанта не найден в контейнере.")
        else:
            print(f"Неизвестный SID type: {sid.name}")
    return df

    # df.write_excel("signers.xlsx")

# if __name__ == "__main__":
#     path = "Пакет независимости РБА 2412.doc.sig"
#     der = load_cms_der_from_pem(path)
#     parse_cms_signers(der, path)


def process_path_dir(path_all: Path, df: pl.DataFrame):
    for path in path_all.iterdir():
        if path.is_file():
            if path.suffix == '.sig':
                der = load_cms_der_from_pem(path)
                df.vstack(parse_cms_signers(der, path), in_place=True)
        elif path.is_dir():
            process_path_dir(path, df)
    return df

def process_signers(path_str: str) -> str: 
    # print(path_list)
    print(path_str)
    path = Path(path_str)
    df = pl.DataFrame()
    if path.is_dir():
        df = process_path_dir(path, df)
    else:
        der = load_cms_der_from_pem(path)
        df = parse_cms_signers(der, path)
    # for path in path_list:
    #     path = Path(path)
    #     if path.is_file():
    #         if path.suffix == '.sig':
    #             der = load_cms_der_from_pem(path)
    #             df.vstack(parse_cms_signers(der, path), in_place=True)
    tmp_name = TMP_DIR / f'result_{int(time())}.xlsx'
    df.write_excel(tmp_name)
    return str(tmp_name)
            
