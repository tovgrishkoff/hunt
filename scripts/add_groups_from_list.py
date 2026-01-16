#!/usr/bin/env python3
"""
Скрипт для добавления групп из списка ссылок в БД
"""
import sys
import re
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

# Используем shared.database для совместимости с account-manager
from shared.database.session import SessionLocal
from shared.database.models import Group

def normalize_group_link(link: str) -> str:
    """
    Нормализация ссылки на группу
    
    Преобразует:
    - t.me/groupname -> @groupname
    - https://t.me/groupname -> @groupname
    - groupname -> @groupname
    - @groupname -> @groupname (без изменений)
    """
    link = link.strip()
    
    # Убираем протокол
    if link.startswith('https://'):
        link = link[8:]
    elif link.startswith('http://'):
        link = link[7:]
    
    # Убираем t.me/
    if link.startswith('t.me/'):
        link = link[5:]
    elif link.startswith('telegram.me/'):
        link = link[12:]
    
    # Убираем параметры (например, ?start=...)
    if '?' in link:
        link = link.split('?')[0]
    
    # Убираем / в конце
    if link.endswith('/'):
        link = link[:-1]
    
    # Обработка invite ссылок вида +DXaf8gqY4TA4Yjg6
    if link.startswith('+'):
        # Это invite hash, пропускаем
        return None
    
    # Добавляем @ если нужно
    if not link.startswith('@'):
        link = '@' + link
    
    return link

def add_groups_to_db(groups_list: list, niche: str = 'bali'):
    """
    Добавление групп из списка в БД
    
    Args:
        groups_list: Список ссылок на группы
        niche: Ниша для групп
    """
    db = SessionLocal()
    try:
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        for group_link in groups_list:
            try:
                normalized = normalize_group_link(group_link)
                
                if not normalized:
                    print(f"  ⚠️ Пропущена ссылка (invite hash или невалидная): {group_link}")
                    skipped_count += 1
                    continue
                
                # Проверяем, существует ли группа в БД
                existing = db.query(Group).filter(Group.username == normalized).first()
                
                if existing:
                    # Обновляем статус на 'new' если он был другой
                    if existing.status != 'new':
                        existing.status = 'new'
                        existing.niche = niche
                        db.commit()
                        print(f"  🔄 Обновлена группа {normalized} -> статус 'new'")
                        added_count += 1
                    else:
                        print(f"  ⏭️  Группа {normalized} уже существует со статусом 'new'")
                        skipped_count += 1
                    continue
                
                # Создаем новую группу
                new_group = Group(
                    username=normalized,
                    title=normalized.replace('@', '').replace('_', ' ').title(),
                    niche=niche,
                    status='new',  # Статус 'new' - Joiner подхватит
                )
                
                db.add(new_group)
                db.commit()
                added_count += 1
                print(f"  ✅ Добавлена группа: {normalized}")
                
            except Exception as e:
                db.rollback()
                print(f"  ❌ Ошибка при добавлении {group_link}: {e}")
                error_count += 1
                continue
        
        print("\n" + "=" * 80)
        print(f"📊 РЕЗУЛЬТАТ:")
        print(f"  ✅ Добавлено/обновлено: {added_count}")
        print(f"  ⏭️  Пропущено (уже есть): {skipped_count}")
        print(f"  ❌ Ошибок: {error_count}")
        print("=" * 80)
    finally:
        db.close()

def main():
    """Точка входа"""
    # Список групп из запроса пользователя
    groups_list = [
        "https://t.me/events_travels_group",
        "https://t.me/russians_in_bali",
        "https://t.me/rent_in_bali",
        "https://t.me/uslugi_na_bali",
        "https://t.me/balichatik",
        "https://t.me/bali_chatus",
        "https://t.me/bali_ua/",
        "https://t.me/balichat_it",
        "https://t.me/balichange",
        "https://t.me/balidating",
        "https://t.me/balimc",
        "https://t.me/bali_visa",
        "https://t.me/balihealth",
        "https://t.me/buildbali",
        "https://t.me/balibc",
        "https://t.me/investbali",
        "https://t.me/BaliStartups",
        "https://t.me/balisp",
        "https://t.me/seobali",
        "https://t.me/balibeauty",
        "https://t.me/baliyoga",
        "http://t.me/balichatarenda",
        "http://t.me/Belkin_Bali_Rent",
        "https://t.me/balichat",
        "http://t.me/balirental",
        "http://t.me/balichatroommates",
        "https://t.me/arenda_bali_1",
        "https://t.me/VillaUbud",
        "http://t.me/balichatsurfing",
        "http://t.me/Arenda_Bali_Villy",
        "https://t.me/balichat_bukit",
        "https://t.me/bali_dom",
        "http://t.me/balichat_photovideo",
        "https://t.me/arendabali",
        "http://t.me/bali_arenda1",
        "https://t.me/cangguchat",
        "https://t.me/balichatservices",
        "https://t.me/blizkie_bali_avito",
        "http://t.me/BaliHouseRent",
        "https://t.me/BaliLoveProp",
        "https://t.me/baliwomens",
        "https://t.me/balichildren",
        "https://t.me/balirentapart",
        "https://t.me/pure_bali",
        "https://t.me/SIBTravel_Bali",
        "https://t.me/balyt",
        "https://t.me/balilv",
        "https://t.me/bali_party",
        "https://t.me/obmen_g_eneg",
        "https://t.me/balifruits",
        "https://t.me/onerealestatebali",
        "https://t.me/jobsbali",
        "https://t.me/balichat_ladymarket",
        "https://t.me/sosedprivetbali",
        "https://t.me/baligames",
        "https://t.me/balisurfer",
        "https://t.me/eventsbali",
        "https://t.me/baliauto",
        "https://t.me/balibike",
        "https://t.me/glavdubai",
        "https://t.me/balisale",
        "https://t.me/baliservice",
        "https://t.me/baliontheway",
        "https://t.me/baliexchanges",
        "https://t.me/balipackage",
        "http://t.me/Belkin_Bali_Service",
        "http://t.me/balioby",
        "https://t.me/toursbali",
        "https://t.me/balifood",
        "http://t.me/lombok_chat",
        "http://t.me/canggu_bali_2016",
        "http://t.me/balichat_woman",
        "http://t.me/gdansk_gdynia_sopot_chat",
        "http://t.me/balibutler",
        "http://t.me/baliof",
        "http://t.me/balichatnash",
        "http://t.me/voprosBali",
        "http://t.me/rabota_bali",
        "https://t.me/balibara",
        "https://t.me/+DXaf8gqY4TA4Yjg6",
        "https://t.me/mafiaonbali",
        "https://t.me/bali_invest_group",
        "https://t.me/baly_ads",
        "https://t.me/surfing_chatik",
        "https://t.me/BikeBalifornia",
        "https://t.me/GiliBali",
        "https://t.me/ChanguBalifornia",
        "https://t.me/bali_kuta",
        "https://t.me/Belkin_Bali_Chat",
        "https://t.me/BaliJob",
        "https://t.me/ArendaBalifornia",
        "https://t.me/ubud_2",
        "https://t.me/balichatgilinow",
        "https://t.me/balichatfit",
        "https://t.me/balichat_amedlovina",
        "https://t.me/balichatparties",
        "https://t.me/bali_russia_choogl",
        "https://t.me/balimotocats",
        "https://t.me/BaliLives",
        "https://t.me/afisha_bali2",
        "https://t.me/balichat_canggu",
        "https://t.me/balichatmoto",
        "https://t.me/networking_bali",
        "https://t.me/surfculture",
        "https://t.me/Bali_Top_Chat",
        "https://t.me/buysellbali",
        "https://t.me/affiliate_marketing_bali",
        "https://t.me/real_estate_balii",
        "https://t.me/villasvalley",
        "https://t.me/balivillla",
        "https://t.me/rentallbali",
        "https://t.me/Villa_Bali_Arenda_1",
        "https://t.me/BALI_BIG_HOUSE",
        "https://t.me/villa_11_20_mln",
        "https://t.me/balilovebike",
        "https://t.me/balibikes",
        "https://t.me/rentbalibike",
        "https://t.me/rent4ubali",
        "https://t.me/WorkExBali",
        "https://t.me/sellersmedia_bali",
        "https://t.me/BaliUrbanNet",
        "https://t.me/bali_money_obmen1",
        "https://t.me/obmen_balii",
        "https://t.me/AsiaObmen",
        "https://t.me/baliiobmen",
        "https://t.me/balimoney",
        "https://t.me/bali_insurance",
        "https://t.me/bali_flights",
        "https://t.me/bali_longstay",
        "https://t.me/bali_startups_founders",
        "https://t.me/bali_digitalnomads",
        "https://t.me/bali_vloggers",
        "https://t.me/bali_job_board",
        "https://t.me/bali_real_estate_news",
        "https://t.me/PhuketParadis",
        "https://t.me/vmestenaphukete",
        "https://t.me/forum_phuket",
        "https://t.me/Phuket_ads_Thailand",
        "https://t.me/samui_live",
        "https://t.me/samui_chat_znakomstva",
        "https://t.me/Samui_tourist"
    ]
    
    print("=" * 80)
    print("🚀 ДОБАВЛЕНИЕ ГРУПП ИЗ СПИСКА В БД")
    print("=" * 80)
    print(f"📋 Всего ссылок: {len(groups_list)}")
    print("=" * 80)
    print()
    
    add_groups_to_db(groups_list, niche='bali')
    
    print("\n✅ Готово! Группы добавлены в БД со статусом 'new'")
    print("   Account Manager автоматически начнет в них вступать по расписанию")

if __name__ == "__main__":
    main()
