# РФ-ориентированный датасет для обучения TFLite модели SpamBlocker

## Структура

```
datasets/ru/
├── raw/                              # Исходные данные из источников
│   ├── ru_reputation_raw.csv         # Агрегированная репутация номеров (основной raw)
│   ├── ru_reputation_evidence.csv    # Аудит-трейл: все записи с деталями парсинга
│   ├── whitelist_official_ru.csv     # Официальные номера банков/служб
│   ├── blacklist_moshelovka.csv      # Мошеловка ОНФ (чёрный список)
│   ├── blacklist_spravportal.csv     # SpravPortal (чёрный список)
│   ├── reviews_neberitrubku.csv      # Не бери трубку (отзывы)
│   ├── reviews_zvonili.csv           # Zvonili.com (отзывы)
│   ├── ru_numbering_plan.csv         # План нумерации РФ (Россвязь)
│   ├── crawler_state.json            # Состояние краулера (resume)
│   └── cache/                        # HTML-кеш краулера (gitignore)
├── processed/                        # Обработанные данные для обучения
│   ├── ru_tflite_features.csv        # 32 компактных признака + label
│   ├── ru_metadata_features.csv      # Полные metadata-признаки
│   ├── ru_call_features.csv          # Расширенные call-признаки
│   ├── ru_numbers_labeled.csv        # Номера с labels ALLOW/WARN/BLOCK
│   └── ru_reputation_raw.csv         # Копия raw для processed-пайплайна
├── reports/                          # Отчёты обучения (gitignore)
└── README.md
```

## Форматы CSV

### raw/ru_reputation_raw.csv
Основной файл репутации, собирается краулером из 6 источников:
```
normalized_number,source,category,confidence,search_volume,source_reliability,view_count,related_count,detail_date,page_title
+79854430013,moshelovka,Телефонное мошенничество,1.0,1500,0.95,1500,3,2025-01-15,Мошенник 9854430013
```

### raw/ru_reputation_evidence.csv
Аудит-трейл всех парсинг-записей (для отладки и воспроизводимости):
```
normalized_number,source,category,confidence,full_text,page_title,view_count,related_count,source_reliability,detail_date,fraud_hits,warn_hits
```

### raw/whitelist_official_ru.csv
```
normalized_number,name,category
+74957754747,Сбербанк,bank
+78005553535,Сбербанк,bank
+74956444444,МТС,support
+7101,Пожарная,emergency
```

### raw/ru_numbering_plan.csv
```
def_code,start_number,end_number,operator,region,capacity,number_type
916,0,999999,МТС,Москва,1000000,mobile
495,0,9999999,МГТС,Москва,10000000,landline
800,0,9999999,Телефон свободный,Россия,10000000,tollfree
```

### processed/ru_tflite_features.csv
32 компактных признака (0.0–1.0) + label (0=ALLOW, 1=WARN, 2=BLOCK):
```
isContact,isRuNumber,isForeignNumber,isShortCode,isStandardLength,is8800,isGeographical,isMobile,isValidRuRange,spoofingPrefixFlag,digitEntropy,repeatDigitRatio,maxSameDigitRun,beautifulNumberFlag,prefixRisk,callFrequency7d,isNightCall,recentBankGov,recentMarketplace,recentMessenger,wasRejected,inBlacklist,inAllowlist,isHiddenNumber,callerVerification,userVulnerability,businessActivity,permissionsAvailable,reputationScore,sourceConfidence,label
0,1,0,0,1,0,0,1,1,0,0.85,0.1,2,0,0.8,0.3,0,1,0,0,0,1,0,0,1,0.5,0.3,1,0.7,0.95,2
```

### processed/ru_numbers_labeled.csv
```
normalized_number,label,weight,source
+79001234567,BLOCK,2.0,moshelovka
+79161234567,WARN,1.0,zvonili
+74957754747,ALLOW,2.0,whitelist_official
```

## Источники данных (краулер)

| Источник | source_reliability | Тип | URL |
|----------|-------------------|-----|-----|
| spravportal | 0.86 | API/Scraping | spravportal.ru |
| callfilter | 0.70 | Scraping | callfilter.ru |
| zvonili | 0.62 | Scraping | zvonili.com |
| moshelovka | 0.95 | Blacklist | moshelovka.onf.ru |
| bloha | 0.75 | Scraping | bloha.ru |
| getscam | 0.55 | Scraping | getscam.org |

## Как собрать датасет

```powershell
# 1. Проверка окружения
.\run.ps1 doctor

# 2. Скачать план нумерации РФ
python scripts/ru_numbering_plan.py

# 3. Запустить краулер (ночной сбор репутации)
python scripts/ru_reputation_crawler.py

# 4. Построить metadata-датасет
.\run.ps1 build-dataset

# 5. Обучить модели + экспорт TFLite
.\run.ps1 train -ExportTflite -Plots

# 6. Проверка качества данных
.\run.ps1 quality
```
