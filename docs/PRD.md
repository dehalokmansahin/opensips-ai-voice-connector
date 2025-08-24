# **Yüksek Ölçekli, Şirket İçi Gerçek Zamanlı Ses Yapay Zekası için Çekirdek Mimarisi Taslağı**

## **Bölüm I: Yüksek Performanslı Bir Pipecat Ses Hattı için Mühendislikte En İyi Uygulamalar**

Bu belge, Pipecat çerçevesinin temel orkestrasyon yeteneklerini kullanarak yüksek performanslı, gerçek zamanlı bir yapay zeka ses bağlayıcısı geliştirmek ve ölçeklendirmek için odaklanmış bir teknik rehber sunmaktadır. Belge, Pipecat'in asenkron pipeline mimarisi, özel bileşen entegrasyonu ve gözlemlenebilirlik (observability) konularındaki en iyi uygulamaları ele almaktadır. Son bölüm, bu mühendislik ilkelerini, kurumsal telefon sistemleri için özel olarak tasarlanmış bir yapay zeka ses çözümü için revize edilmiş bir Ürün Gereksinim Belgesi (PRD) içinde birleştirmektedir.

### **Bölüm 1: Pipecat Pipeline Yaşam Döngüsü ve Orkestrasyon**

Üretim düzeyinde bir Pipecat uygulaması, temel pipeline yürütmenin ötesinde, arama yaşam döngüsünün, kaynak yönetiminin ve hataların zarif bir şekilde yönetilmesini gerektirir. Çerçeve, bu karmaşıklıkları yönetmek için sağlam temel yapı taşları sunar.

#### **1.1. PipelineTask ve PipelineRunner: Temel Yürütme ve Kaynak Yönetimi**

Bir Pipecat uygulamasının yürütülmesinin çekirdeği PipelineTask ve PipelineRunner sınıfları tarafından yönetilir. Bir üretim sistemi, bir aramanın tüm yaşam döngüsünü – başlangıç, normal operasyon ve sonlandırma – güvenilir bir şekilde yönetmelidir.

* **PipelineTask**: Belirli bir pipeline örneğinin yürütülmesini düzenleyen merkezi nesnedir. Gelen ses çerçevelerini (frames) yönlendirmekten, pipeline içindeki işlemcilerin (processors) durumunu yönetmekten ve kaynakların temizlenmesinden sorumludur.  
* **PipelineRunner**: Bir veya daha fazla PipelineTask örneğini yürütmek için sağlam bir ortam sağlayan üst düzey bir yöneticidir. Üretim ortamlarındaki en kritik işlevi, SIGINT ve SIGTERM gibi sistem sinyallerini işleme yeteneğidir. Bu, konteynerli bir ortamda uygulamanın düzgün bir şekilde kapatılmasını (graceful shutdown) ve aktif aramaların aniden kesilmemesini sağlar.

Telefon kaynaklarını yönetmek için PipelineTask kurucusundaki şu parametreler kritik öneme sahiptir:

* **idle\_timeout\_secs**: Bu parametre, sahipsiz veya askıda kalmış pipeline'ların sistem kaynaklarını süresiz olarak tüketmesini önler. Bir arayan aniden kapatırsa veya hat sessizleşirse, bu zaman aşımı, ilgili pipeline'ın belirli bir süre sonra otomatik olarak sonlandırılmasını sağlar.  
* **conversation\_id**: Her PipelineTask'a benzersiz bir tanımlayıcı atamak, gözlemlenebilirlik (observability) için temel bir en iyi uygulamadır. Bu kimlik, günlükler ve izleme sistemleri (örneğin, OpenTelemetry) aracılığıyla yayılarak, tek bir aramanın yaşam döngüsünün hata ayıklama ve analiz için tamamen yeniden oluşturulmasına olanak tanır.

**En İyi Uygulama:** Düzgün kapatma (graceful shutdown) için sinyal işlemeyi doğru şekilde yapılandıran merkezi bir PipelineRunner uygulayın. Her gelen SIP araması için yeni bir PipelineTask örneği oluşturun. Bu görevi, izleme için benzersiz bir conversation\_id ve kaynak sızıntılarını önlemek için makul bir idle\_timeout\_secs ile yapılandırın.

#### **1.2. Özel Durum Yönetimi ve İş Mantığı**

Pipecat Flows kullanılmadığında, konuşma durumu ve iş mantığı yönetimi doğrudan pipeline içinde özel servisler veya işlemciler aracılığıyla gerçekleştirilmelidir. Bu yaklaşım, iş mantığı üzerinde tam kontrol ve esneklik sağlar.

Durum, pipeline'a enjekte edilen ve TransportParams aracılığıyla tüm işlemciler tarafından erişilebilen paylaşılan bir "bağlam" (context) nesnesi içinde tutulabilir. Bu nesne, kullanıcı kimliği, konuşma geçmişinin ilgili kısımları, toplanan varlıklar (entities) ve iş akışının mevcut durumu gibi bilgileri içerebilir.

**En İyi Uygulama:** Her arama için, arama süresince durumu koruyacak bir "bağlam yönetimi" servisi oluşturun. Bu servis, PipelineTask başlatıldığında oluşturulmalı ve pipeline'daki tüm özel işlemcilere (custom processors) referans olarak geçirilmelidir. LLM'den bir yanıt geldiğinde, özel bir "niyet ayrıştırma" (intent parsing) işlemcisi bu yanıtı analiz edebilir, durumu güncelleyebilir ve bir sonraki eylemi (örneğin, bir API çağırmak veya belirli bir yanıtı sentezlemek) tetikleyebilir. Bu, durum makinesi mantığını Flows olmadan, daha esnek bir şekilde uygulamanıza olanak tanır.

#### **1.3. Sağlam Hata Kurtarma ve Kesinti Yönetimi**

Bir üretim sistemi, ağ hataları veya hizmet zaman aşımları gibi arızalara karşı dayanıklı olmalıdır.

* **Hata Kurtarma:** Pipecat'in olay güdümlü mimarisi, bu arızaları yönetmek için kancalar sağlar. PipelineTask sınıfı on\_pipeline\_started, on\_pipeline\_stopped gibi genel olay işleyicileri sunar. Daha da önemlisi, LLM hizmet işlemcisinin on\_completion\_timeout gibi belirli olay işleyicileri, dil modeli zamanında yanıt vermediğinde özel kurtarma stratejileri uygulamanıza olanak tanır.  
* **Kesinti Yönetimi:** Doğal konuşma akışını sağlamak için kesintileri yönetmek önemlidir. PipelineParams içinde allow\_interruptions=True olarak ayarlanarak kesintiler etkinleştirilebilir. MinWordsInterruptionStrategy gibi bir strateji, kullanıcının "hı-hı", "evet" gibi kısa geri bildirimlerinin (backchanneling) botun konuşmasını gereksiz yere kesmesini önler.

**En İyi Uygulama:** Kritik hata noktaları için olay işleyicileri uygulayın. Örneğin, bir on\_completion\_timeout durumunda, kullanıcıyı gecikme hakkında bilgilendirmek için bir TTSSpeakFrame gönderin ve iş mantığınızı bir kurtarma yoluna yönlendirin. Kesinti yönetimi için MinWordsInterruptionStrategy kullanarak, kısa geri bildirimleri filtrelerken gerçek konuşma girişimlerine duyarlı kalarak sağlam bir denge kurun.

### **Bölüm 2: Düşük Gecikme ve Gerçek Zamanlı Yanıt Verme için Mimari Tasarım**

Bir sesli yapay zeka asistanında olumlu bir kullanıcı deneyimi için en önemli faktör gecikmedir. Bunu başarmak, sistemin her bileşenini optimize eden bütünsel bir yaklaşım gerektirir.

#### **2.1. Uçtan Uca Gecikmeyi Ayrıştırma ve Ölçme (Observability)**

"Sesten sese" gecikme, birkaç aşamanın toplamıdır: Ağ gecikmesi, ASR işleme, LLM işleme (genellikle en büyük değişken) ve TTS işleme. Optimizasyonun ilk adımı ölçümdür.  
Pipecat, PipelineParams içinde enable\_metrics=True olarak ayarlanarak etkinleştirilebilen yerleşik metrikler sağlar. Bu, pipeline'daki her hizmet için İlk Bayta Kadar Geçen Süre (TTFB) gibi kritik performans göstergelerini günlüğe kaydeder. Bu metrikler, sistemdeki darboğazları belirlemek için çok önemlidir.  
**En İyi Uygulama:** Her arama için Pipecat'in performans metriklerini sistematik olarak etkinleştirin, günlüğe kaydedin ve izleyin. Bu verileri toplamak ve her hizmet için gecikme dağılımlarını (P50, P90, P99) görselleştiren panolar oluşturmak için OpenTelemetry gibi araçları kullanın. Bu, hedeflenen optimizasyon çabalarına olanak tanır.

#### **2.2. Ses Hattı ve Taşıma Katmanını Optimize Etme**

Düşük gecikmeli bir sistemin temeli verimli ses yönetimidir. Mevcut sistemin 20 ms'lik parçalar halinde PCMU/8000 kodekini kullanması bir telefon standardıdır. Ancak, çoğu modern ASR modelinin 16kHz örnekleme hızlarında daha doğru performans gösterdiği unutulmamalıdır.  
Şirket içi bir dağıtımda, tüm bileşenlerin (OpenSIPS, Pipecat, ASR/LLM/TTS modelleri) aynı fiziksel veri merkezinde, düşük gecikmeli bir yerel ağ üzerinde bulunması ağ gecikmesini en aza indirmek için kritiktir.  
**En İyi Uygulama:**

* **Aynı Yerde Bulunma (Co-location):** Tüm bileşenlerin aynı veri merkezinde dağıtıldığından emin olun.  
* **Kodek ve Örnekleme Hızı:** Seçilen ASR modelinin performansını 8kHz ve 16kHz girişle test edin. Doğruluk artışı önemliyse, 16kHz'e geçişi veya pipeline içinde gerçek zamanlı yukarı örneklemeyi (upsampling) değerlendirin.  
* **Arabelleğe Almayı En Aza İndirme:** Gelen her 20 ms'lik ses parçasını anında işleyerek akışın gerçek zamanlı doğasını korumak için tüm bileşenlerde arabelleğe almayı en aza indirin.

#### **2.3. ASR, LLM ve TTS için Hizmet Düzeyi Optimizasyonları**

* **ASR Optimizasyonu:** ASR hizmeti, oluşturuldukça ara transkripsiyon sonuçları sağlayan akış modunda çalışmalıdır. Bu, LLM'nin kullanıcı cümlesini bitirmeden işlemeye başlamasına olanak tanır.  
* **LLM Optimizasyonu:** LLM için en kritik metrik **İlk Jetona Kadar Geçen Süre (TTFT)**'dir. Şirket içi dağıtımlar için, nicelenmiş modeller (örneğin, 4-bit quantization) kullanmak, uyumlu donanımda (GPU'lar) çıkarım hızını önemli ölçüde artırabilir.  
* **TTS Optimizasyonu:** TTS hizmeti, LLM'den ilk jetonu alır almaz konuşma sentezlemeye başlamalıdır (akış girişi). Bu, botun sesinin, LLM'nin oluşturma süreciyle paralel olarak kullanıcıya geri akıtılmasına olanak tanır.

**En İyi Uygulama:**

* **Spekülatif Yürütme:** Harici bir API çağırmayı gerektiren durumlarda, önce "Bir saniye, kontrol ediyorum..." gibi hızlı bir dolgu yanıtı oluşturun ve TTS'e gönderin. Eş zamanlı olarak API çağrısını yürütün. Sonuç döndüğünde, nihai yanıtı oluşturmak için LLM'ye geri besleyin. Bu, API gecikmesini konuşulan dolgu ifadesinin arkasına gizler.

### **Bölüm 3: Akışlı Ses Yapay Zekası için Gelişmiş Asenkron Python**

Pipecat, Python'un asyncio kütüphanesi üzerine kurulmuştur ve kalıplarını doğru kullanmak, ölçeklenebilir bir uygulama oluşturmak için gereklidir. Uygulama temelde G/Ç'ye bağlıdır (ağ paketleri, API yanıtları beklemek).

#### **3.1. asyncio'nun Çekirdeği: Olay Döngüleri ve Korutinler**

asyncio, tek bir iş parçacığında işbirlikçi çoklu görev (cooperative multitasking) aracılığıyla binlerce eşzamanlı bağlantıyı verimli bir şekilde yönetir. Bir korutin (async def), G/Ç beklerken (await) yürütmeyi duraklatır ve olay döngüsünün diğer görevleri çalıştırmasına izin verir. Bu model, yüksek sayıda eşzamanlı arama için son derece verimlidir.

**En İyi Uygulama:** Uygulamanın tüm kod tabanında tutarlı bir şekilde async/await sözdizimini kullanın. time.sleep() veya requests.get() gibi engelleme (blocking) çağrılarından kesinlikle kaçının; bunların yerine asyncio.sleep() ve aiohttp gibi asenkron alternatiflerini kullanın.

#### **3.2. Ağ G/Ç'sini ve İşlemeyi Ayırmak için Üretici-Tüketici Deseni**

Ağdan RTP paketlerini almak (üretici) ile bunları yapay zeka pipeline'ında işlemek (tüketici) farklı hızlarda çalışabilir. asyncio.Queue kullanarak uygulanan üretici-tüketici deseni, bu iki süreci birbirinden ayırır.

* **Üretici:** RTP soketinden ses paketlerini alır ve bunları bir asyncio.Queue'ya yerleştirir.  
* **Tüketici:** Kuyruktan ses paketlerini alır ve bunları Pipecat pipeline'ına besler.

Bu mimari, ağdaki titreşimlere (jitter) ve yapay zeka modeli gecikmesindeki değişkenliklere karşı sistemi daha dayanıklı hale getiren bir tampon oluşturur.

**En İyi Uygulama:** Her arama için, gelen ses çerçevelerini bir asyncio.Queue'ya yerleştiren adanmış bir üretici korutini uygulayın. Pipeline'ı yöneten tüketici korutini bu kuyruktan okumalıdır. Ağır yük altında kontrolsüz bellek büyümesini önlemek ve geri basınç (backpressure) uygulamak için sınırlı boyutlu bir kuyruk (asyncio.Queue(maxsize=...)) kullanın.

### **Bölüm 6: Temel Özellikler ve Fonksiyonel Gereksinimler**

#### **6.1. Telefon ve SIP Bağlantısı**

* **REQ-001:** Sistem, standart şirket içi PBX sistemleriyle (Cisco Unified Communications Manager dahil) entegrasyon için bir SIP trunk arayüzü sağlamalıdır.  
* **REQ-002:** Sistem, G.711 μ-law (PCMU/8000) kodekini kullanarak RTP medya akışlarını doğal olarak yönetmelidir.  
* **REQ-003:** Sistem, gelen aramaları kapasiteye duyarlı bir algoritma kullanarak bir yapay zeka işleme düğümleri kümesi arasında dağıtabilen yerleşik, yüksek erişilebilir bir SIP yük dengeleyici (OpenSIPS tabanlı) içermelidir.

#### **6.2. Gerçek Zamanlı Yapay Zeka Pipeline Orkestrasyonu**

* **REQ-004:** Sistem, ASR, LLM ve TTS hizmetlerinin tamamen akışlı, gerçek zamanlı bir pipeline'ını düzenlemelidir.  
* **REQ-005:** Sistem, müşterilerin kendi şirket içi ASR, LLM ve TTS modellerini özel işlemciler (custom processors) aracılığıyla entegre etmelerine olanak tanıyan tak-çıkar bir hizmet mimarisi sağlamalıdır.  
* **REQ-006:** Sistem, geliştiricilerin pipeline'a özel veri dönüştürme, iş mantığı yürütme ve harici API çağırma adımları eklemesine olanak tanıyan özel işlemcilerin oluşturulmasını desteklemelidir.  
* **REQ-007:** Sistem, pipeline içindeki farklı veri türlerini (örneğin, ses, metin, JSON) işlemek için genişletilebilir serileştiriciler (serializers) sağlamalıdır.

#### **6.3. Gözlemlenebilirlik ve İzleme (RTVI)**

* **REQ-008:** Sistem, arama başına ve hizmet başına gecikme metrikleri (TTFB, TTFT), aktif arama sayısı ve kaynak kullanımı dahil olmak üzere kapsamlı performans metrikleri sunmalıdır.  
* **REQ-009:** Sistem, Grafana gibi kurumsal izleme sistemleriyle entegrasyon için Prometheus uyumlu bir /metrics uç noktası sunmalıdır.  
* **REQ-010:** Sistem, her aramanın yaşam döngüsünü izlemek ve hata ayıklamak için OpenTelemetry standartlarıyla uyumlu, dağıtılmış izleme (distributed tracing) yeteneklerini desteklemelidir.

#### **6.4. Dağıtım ve Paketleme**

* **REQ-011:** Ürün, Docker ve Docker Compose kullanılarak kolayca dağıtılabilmesi için gerekli yapıtları (artifacts) sağlayacaktır.  
* **REQ-012:** Ürün, Kubernetes/K3s ortamlarına dağıtımı basitleştirmek için gerekli yapıtları (örneğin, Helm şeması) sağlayacaktır.

### **Bölüm 7: Fonksiyonel Olmayan Gereksinimler**

#### **7.1. Performans ve Gecikme**

| Metrik Kategorisi | Metrik | Hedef (P90) |
| :---- | :---- | :---- |
| **LLM** | İlk Jetona Kadar Geçen Süre (TTFT) | \< 500 ms |
| **TTS** | İlk Bayta Kadar Geçen Süre (TTFB) | \< 200 ms |
| **Uçtan Uca** | Sesten Sese Gecikme | \< 800 ms |

* **NFR-001 (Eşzamanlılık):** Her standart işleme düğümü, yukarıda tanımlanan P90 gecikme hedeflerini korurken en az 100 eşzamanlı aramayı desteklemelidir.

### **Bölüm 8: Kapsam Dışı**

Aşağıdaki özellikler ve yetenekler v1.0 için açıkça kapsam dışıdır:

* **Bulut Dağıtımı:** Ürün, yönetilen bir SaaS, PaaS veya IaaS çözümü olarak sunulmayacaktır.  
* **Gelişmiş Konuşma Akışı Yönetimi:** Ürün, Pipecat Flows gibi yerleşik, durum makinesi tabanlı bir konuşma yönetimi çerçevesi içermeyecektir. Geliştiriciler, kendi iş mantıklarını özel işlemciler aracılığıyla uygulamaktan sorumlu olacaktır.  
* **Kapsamlı Güvenlik Özellikleri:** Uçtan uca şifreleme (TLS/SRTP), Oturum Sınır Denetleyicisi (SBC) entegrasyonu ve gelişmiş ağ güvenliği yapılandırmaları bu sürümün kapsamı dışındadır ve müşterinin mevcut altyapısına bırakılmıştır.