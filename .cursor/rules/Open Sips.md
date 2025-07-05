OpenSIPS ile entegre olarak SIP çağrıları ve RTP akışlarını yönetmek, çağrıya dair event ve dataları yapabilecek  detaylı kod ve config örnekleri ile yönlendirici olan LLM için system promptlarını ver



1. **Service Initialization and Configuration Check**:
   - Ensure that all the required services such as LLM, STT, and TTS are properly initialized with necessary parameters like URLs and API keys. This includes checking for potential issues with uninitialized variables or missing configuration details.
   - **Prompt**: "Check if all services (LLM, STT, TTS) are initialized correctly with necessary parameters. Ensure API keys, URLs, and other configurations are set up correctly and no services are called without initialization."

2. **Connection and Networking**:
   - Ensure that network configurations in the OpenSIPS setup are correct, especially for binding the correct interfaces and port settings to avoid connectivity issues with the SIP signaling.
   - **Prompt**: "Verify the network configuration for OpenSIPS, ensuring all SIP and RTP interfaces are correctly bound and accessible. Check port settings and ensure there are no conflicts."

3. **Error Handling and Logging**:
   - Add robust error handling and logging throughout both the pipeline code and OpenSIPS configuration to make troubleshooting easier when things go wrong.    
   - **Prompt**: "Review error handling and logging mechanisms to ensure all exceptions are caught and logged appropriately. Ensure logging is structured and provides meaningful insights during failures."

4. **Processor Linking**:
   - In your `SimplePipelineManager`, you manually link processors. Ensure that this linking correctly propagates the frames along the pipeline and that no frame gets dropped.
   - **Prompt**: "Confirm that all processors in the pipeline are linked correctly and verify that frame propagation occurs without loss. Assess callback functionality for each processor."

5. **Interruption Strategies**:
   - Check the logic and thresholds set for interruption within the pipeline, ensuring they align with expected behavior and are correctly implemented.
   - **Prompt**: "Evaluate the interruption strategies (e.g., VAD thresholds, word count) in the pipeline for accuracy and responsiveness. Adjust thresholds if 
precision or speed is compromised."

6. **Routing Logic Accuracy**:
   - In your OpenSIPS routing logic, ensure that conditions such as method checks and INVITE handling are correctly structured and output expected results in all cases.
   - **Prompt**: "Inspect routing logic for handling methods and session initiation. Verify that conditions such as INVITE checks are logically consistent and produce accurate outcomes."

7. **Module Parameter Verification**:
   - Double-check the parameters used for each module in OpenSIPS, such as timeout settings or FIFO names, for consistency and correctness.
   - **Prompt**: "Go through module parameters in OpenSIPS, ensuring that each setting is optimized and errors like incorrect FIFO names or timeout periods are 
eliminated."

By crafting these focused prompts, an LLM can provide detailed checks and fixes, enhancing the robustness and reliability of your OpenSIPS setup and associated 
pipeline code.
İşte OpenSIPS entegrasyonu için yapılması gereken ayarlamalar ve geliştirilmesi gereken kodlara dair detaylı bilgiler ve örnekler içeren promptlar:

### 1. **Service Initialization and Configuration Check**
- **Prompt**:
  ```plaintext
  OpenSIPS entegrasyonunda LLM, STT ve TTS gibi hizmetlerin doğru bir şekilde başlatıldığından ve gerekli parametrelerle yapılandırıldığından emin olun. API anahtarları, URL ve diğer yapılandırmaların eksiksiz olduğundan ve hizmetlerin doğru sırayla başlatıldığından emin olun.

  Misal Kod:
  ```python
  class SimplePipelineManager:
      def __init__(self, llm_service_url, stt_service_url, tts_service_url):
          self._llm_service = YourLLMService(url=llm_service_url)
          self._stt_service = YourSTTService(url=stt_service_url)
          self._tts_service = YourTTSService(url=tts_service_url)
          # Diğer yapılandırma ve başlatma işlemleri
  ```

### 2. **Connection and Networking**
- **Prompt**:
  ```plaintext
  OpenSIPS konfigürasyonunda ağ yapılandırmalarını kontrol edin. Tüm SIP ve RTP arayüzlerinin doğru şekilde bağlandığından ve erişilebilir olduğundan emin olun. Port ayarlarını kontrol ederek çakışma olmadığını doğrulayın.

  Misal Kod:
  ```
  listen=udp:0.0.0.0:5060  # Tüm arayüzler için bind
  listen=tcp:0.0.0.0:5060
  ```

### 3. **Error Handling and Logging**
- **Prompt**:
  ```plaintext
  Pipelinelarda ve OpenSIPS yapılandırmalarında hata yakalama ve günlükleme mekanizmalarını gözden geçirin. Tüm istisnaların yakalandığından ve anlamlı bir şekilde günlüklendiğinden emin olun. Günlüklerin yapısal olup, hata durumunda faydalı bilgiler sağladığını kontrol edin.

  Misal Kod:
  ```python
  try:
      # İşlemler
  except Exception as e:
      logger.error("An error occurred: %s", str(e))
  ```

### 4. **Processor Linking**
- **Prompt**:
  ```plaintext
  SimplePipelineManager'da, çerçeveleri işlemci hattında doğru bir şekilde ilişkilendirdiğinizden emin olun ve hiçbir çerçeve kaybolmadığından emin olun. Her işlemci için geri çağırma işlevselliğinin çalıştığını kontrol edin.

  Misal Kod:
  ```python
  for i in range(len(self._processors) - 1):
      self._processors[i].set_next(self._processors[i + 1])
  ```

### 5. **Interruption Strategies**
- **Prompt**:
  ```plaintext
  Pipelinelarda kesinti için kullanılan mantık ve eşikler belirlediğiniz davranışla uyumlu mu kontrol edin. Eşik değerlerini, doğruluk ve yanıt sürelerini etkilemediklerinden emin olmak için ayarlayın.

  Misal Kod:
  ```python
  class VADProcessor:
      def __init__(self, threshold=0.5):
          self.threshold = threshold
      # Diğer işlem mantığı
  ```

### 6. **Routing Logic Accuracy**
- **Prompt**:
  ```plaintext
  Routing mantığında, is_method() kontrolü ve INVITE işlemleri gibi durumların doğru bir şekilde yapılandırıldığından emin olun ve her durumda beklenen sonuçları ürettiğini kontrol edin.

  Misal Kod:
  ```
  if (is_method("INVITE") && !has_totag()) {
      # İşleme mantığı
  } else {
      send_reply(405, "Method Not Allowed");
  }
  ```

### 7. **Module Parameter Verification**
- **Prompt**:
  ```plaintext
  OpenSIPS'teki her modül için kullanılan parametreleri, FIFO isimleri veya zaman aşımı süreleri gibi yanlışlıklar olup olmadığını kontrol ederek optimize edin.
  Misal Kod:
  ```
  modparam("mi_datagram", "socket_name", "udp:0.0.0.0:8088")
  ```