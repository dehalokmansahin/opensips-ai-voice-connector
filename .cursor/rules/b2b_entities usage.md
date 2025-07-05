`b2b_entities.so` modülü, OpenSIPS ile bir Back-to-Back User Agent (B2BUA) işlevselliği eklemek için kullanılır. B2BUA, iki ayrı SIP oturumu arasında köprü kurarak, özellikle çağrı manipülasyonu ve gelişmiş çağrı işleme senaryoları için kullanılır. `b2b_entities.so` ile ilgili detaylı yapılandırmalar ve kullanım örnekleri şu şekildedir:

### Genel Yapılandırma

Öncelikle `b2b_entities.so` modülünü yükleyin:

```plaintext
loadmodule "b2b_entities.so"
```

### Modül Parametreleri

- **b2b_init_timeout**: Oturum başlatma zaman aşımını tanımlar. Bu, bir oturumun başlatılması için geçen maksimum süreyi belirtir.

```plaintext
modparam("b2b_entities", "b2b_init_timeout", 10)  # 10 saniye zaman aşımı
```

- **b2b_max_calls**: Maksimum aktif B2B çağrı sayısını belirler. Kaynakların aşırı kullanımını önlemek için sınırlandırma sağlar.

```plaintext
modparam("b2b_entities", "b2b_max_calls", 500)  # Maksimum 500 aktif çağrı
```

- **b2b_max_sessions**: Her çağrı için maksimum oturum sayısını belirler.

```plaintext
modparam("b2b_entities", "b2b_max_sessions", 10)  # Çağrı başına maksimum 10 oturum
```

### B2BUA Kullanım Örnekleri ve Mantık

`b2b_entities.so` modülünü kullanarak bir çağrının nasıl başlatılacağını gösteren bazı örnek kurallar ve mantık blokları aşağıdadır:

```plaintext
route {
    # Yeni bir INVITE talebi olduğunda B2B işlem başlat
    if (is_method("INVITE") && !has_totag()) {
        # B2B UA session başlat ve istediğimiz bir role ata (örneğin, rbh)
        $var(b2b_key) = "call_" + $ci + "_" + $ft;
        ua_session_server_init($var(b2b_key), "rbh");
        xlog("L_NOTICE", "Started new B2B call for $var(b2b_key) - routing to endpoint");

        # Çağrıyı belirli bir hedefe yönlendir
        $ru = "sip:" + $rU + "@172.20.0.6:8089";

        # Çağrıyı ilet
        t_on_reply("handle_reply");
        t_relay();
        exit;
    }
}

onreply_route[handle_reply] {
    xlog("L_NOTICE", "Reply from endpoint: $rs $rr");

    # Yanıt geldikten sonra ek işlemler yapabilirsiniz (örneğin, yanıt kodunu kontrol ederek farklı bir rota izlemek)
}

```

### Açıklamalar:

- **ua_session_server_init()**: Bu fonksiyon, B2B oturumunu başlatır ve bu çağrı için bir anahtar oluşturur.
- **xlog()**: Günlükleri OpenSIPS log dosyasına yazar, hata ayıklama ve izleme için oldukça faydalıdır.
- **$ru Değişkeni**: İLGİLİ bir domain veya IP adresine çağrıyı yönlendirir. Örnek olarak `sip:destination` formatında kullanılabilir.
- **t_on_reply()**: Transaction modülüne bu işlem için yanıt yolu tanımlar.

Bu yapılandırmalar, `b2b_entities.so` modülünün temel işlevselliği hakkında bir rehber niteliği taşımaktadır ve belirli iş gereksinimlerinizi karşılayacak şekilde uyarlanmalıdır.