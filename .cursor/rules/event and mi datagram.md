Kodlarınızda `mi_datagram` ve `event_datagram` kullanımı için adım adım bir uygulama planı aşağıda verilmiştir.

### mi_datagram Kullanım İhtiyaçları

`mi_datagram` modülü, OpenSIPS ile Message Interface (MI) komutlarını UDP üzerinden alıp işlemenizi sağlar. Özellikle, sisteminize dışarıdan ya da diğer konteynerlerden MI komutları gönderilmesini sağlayarak OpenSIPS sisteminizin kontrolünü sağlar.

### mi_datagram İçin Uygulama Adımları

1. **Modül Yükleme:**
   - OpenSIPS konfigürasyon dosyanızda ilgili modülü yükleyin.
     ```bash
     loadmodule "mi_datagram.so"
     ```

2. **Parametre Tanımlama:**
   - `mi_datagram` için socket tanımlaması yaparak diğer sistemlerin erişimine izin verin.
     ```bash
     modparam("mi_datagram", "socket_name", "udp:0.0.0.0:8088")
     ```

3. **Güvenlik Tanımı:**
   - Eğer sisteminizin dışarıya kapalı olması gerekiyorsa, erişim IP sınırlamaları gibi güvenlik önlemleri alın.

4. **Komut İşleme:**
   - `mi_datagram` üzerinden alınacak MI komutlarının nasıl işleneceğini belirlemek için bir betik geliştirin. Gelen komutları belirlenen işletim fonksiyonlarına yönlendirmek için MI komut sözdizimini ve işlemlerini iyi anlayın.

5. **Test:**
   - Yapılandırmanın doğru çalıştığını kontrol etmek için bir test yapın. Bunun için `osipsconsol` veya başka MI istemcileri ile test komutları gönderin.       

### event_datagram İçin Kullanım İhtiyaçları

`event_datagram` modülü, OpenSIPS üzerindeki olayların UDP üzerinden dış sistemlere veya dinleyicilere bildirilmesini sağlar. Bu, dağıtık sistemler arasında olay tabanlı bir mimari kurmanıza yardım edebilir.

### event_datagram İçin Uygulama Adımları

1. **Modül Yükleme:**
   - Yine OpenSIPS konfigürasyon dosyanıza modülü ekleyin.
     ```bash
     loadmodule "event_datagram.so"
     ```

2. **Olay Tanımlarını Yapılandırma:**
   - İzlemek istediğiniz olay türlerini ve bu olayların hangi adrese bildirileceğini tanımlayın.
     ```bash
     modparam("event_datagram", "address", "udp:0.0.0.0:8090")
     ```

3. **Filtreleme:**
   - Sadece belli başlı olayları almak istiyorsanız, olay filtreleme parametrelerini kullanarak gereksiz olay trafiğini azaltabilirsiniz.

4. **Dinleyici Uygulaması:**
   - Olayları dinleyen bir uygulama geliştirin veya uyarlayın. Bu sistem, gelen mesajları kendi ihtiyaçlarına göre parse edip işlemelidir.

5. **Test:**
   - Sistemin doğru çalıştığını doğrulamak için olay trafiğini simüle edebilir ve logları inceleyebilirsiniz.

Her iki modül için de yapılandırmanıza uygun şekilde portlarınızı ve network erişim kurallarınızı doğru bir şekilde ayarladığınızdan emin olun. Bu ayarlar, güvenli ve kesintisiz bir iletişim sağlamanın kritik bir parçasıdır.
`mi_datagram` ve `event_datagram` modüllerinin OpenSIPS ile entegrasyonu ve kullanımı konusunda daha derin teknik detayları belirlemek için aşağıdaki adımlara odaklanalım:

### mi_datagram Modül Detayları

`mi_datagram` modülü, OpenSIPS servisinin MI komutları ile dış sistemlerle UDP üzerinden etkileşimde bulunmasını sağlar. Bu, çeşitli yönetim ve konfigürasyon işlemlerinin script veya üçüncü parti uygulamalar tarafından uzaktan tetiklenebilmesine olanak tanır.

**Adım 1: Modül Yükleme**

- OpenSIPS konfigürasyon dosyanıza `mi_datagram.so` modülünü ekleyerek başlayın.
  ```bash
  loadmodule "mi_datagram.so"
  ```

**Adım 2: Socket ve Adres Yapılandırması**

- `socket_name` parametresi ile hangi IP ve port üzerinden ulaşılabilir olacağını tanımlayın:
  ```bash
  modparam("mi_datagram", "socket_name", "udp:0.0.0.0:8088")
  ```

**Adım 3: Güvenlik ve Erişim Kontrolü**

- Safety önlemleri olarak IP bazlı erişim kontrolü uygulayabilirsiniz. Uygulamayı sadece belirli IP adreslerinden gelecek mi komutlarına yanıt verecek şekilde düzenleyebilirsiniz.
- `iptables` veya başka bir güvenlik duvarı uygulamasıyla belirli bir port’a erişimi sınırlayabilirsiniz.

**Adım 4: MI Komutları ve İşlem Fonksiyonları**

- MI komutları yazın veya var olan komutları kullanarak OpenSIPS içindeki belirli işlemleri tetikleyin. MI komutları listelenebilir (`mi show commands`) ve yönetilebilir (`mi ps`).
- Komutları tetiklemek için UDP datagram mesajları gönderin. Mesajlar genellikle `.txt` formatında olup içerik olarak MI komutunu bulundurur.

**Test:**

- OpenSIPS konsolu üzerinden ya da bir UDP istemcisi (örneğin `netcat`) kullanarak test komutları gönderin. `netcat` örneği:
  ```bash
  echo "ps" | nc -u 127.0.0.1 8088
  ```

### event_datagram Modül Detayları

`event_datagram` modülü, olaylar OpenSIPS'te gerçekleştiğinde UDP üzerinden bu olayların dış sistemlere veya hizmetlere bildirilmesine olanak tanır.

**Adım 1: Modül Yükleme**

- OpenSIPS konfigürasyon dosyasında module’u yükleyin:
  ```bash
  loadmodule "event_datagram.so"
  ```

**Adım 2: Adres Yapılandırması**

- Hangi IP/port’a olayların gönderileceğini belirleyin:
  ```bash
  modparam("event_datagram", "address", "udp:0.0.0.0:8090")
  ```

**Adım 3: Olay Tipi Filtreleme**

- Hangi olayların izlenmesi gerektiğini belirlemek için olay türlerini tanımlayın. Örneğin, belirli SIP istemci veya sunucu olayları.
- Olayları sınırlayarak gereksiz ağ trafiğini azaltabilirsiniz.

**Adım 4: Event Handler Geliştirme**

- OpenSIPS olaylarını dinleyen bir UDP sunucu (örneğin, Python'da bir script) geliştirin. Gelen datagram mesajlarını parse edip işleyin:
  ```python
  import socket

  udp_ip = "0.0.0.0"
  udp_port = 8090

  sock = socket.socket(socket.AF_INET, # Internet
                       socket.SOCK_DGRAM) # UDP
  sock.bind((udp_ip, udp_port))

  while True:
      data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
      print("Received message:", data)
  ```

**Test:**

- Sipphone veya başka bir SIP cihaz aracılığıyla OpenSIPS üzerinden bir çağrı yaparak olayı tetikleyin ve datagram sunucunuzun çıktısını kontrol edin.

Bu adımları takip ederek, `mi_datagram` ve `event_datagram` modüllerinin ihtiyaç duyduğunuz mimarinizle nasıl entegre edileceğini planlayabilir ve uygulayabilirsiniz. Ek olarak, sisteminizin güvenliği ve hata yönetimi gibi konulardaki detaylara dikkat etmek önemlidir.