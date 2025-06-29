#!/usr/bin/env python3
"""
OpenSIPS Event Datagram Listener
Event and MI datagram.md dokümanına göre OpenSIPS olaylarını dinler
"""

import asyncio
import socket
import json
import structlog
from typing import Dict, Any, Optional
from datetime import datetime

logger = structlog.get_logger()

class OpenSIPSEventListener:
    """OpenSIPS Event Datagram dinleyicisi"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8090):
        """
        Initialize event listener
        
        Args:
            host: Listen host
            port: Listen port (config'te event_port = 8090)
        """
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        
        # Event handlers
        self.event_handlers = {
            "OAVC_CALL_EVENT": self.handle_call_event,
            "E_CALL_SETUP": self.handle_call_setup,
            "E_CALL_ANSWERED": self.handle_call_answered,
            "E_CALL_TERMINATED": self.handle_call_terminated,
        }
        
        logger.info("OpenSIPS Event Listener initialized", 
                   host=host, port=port)
    
    async def start(self):
        """Event listener'ı başlat"""
        try:
            # UDP socket oluştur
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.setblocking(False)
            
            self.running = True
            
            logger.info("✅ OpenSIPS Event Listener started", 
                       host=self.host, port=self.port)
            
            # Event listening loop
            while self.running:
                try:
                    # Non-blocking receive with timeout
                    await asyncio.sleep(0.01)  # Small delay to prevent busy waiting
                    
                    try:
                        data, addr = self.socket.recvfrom(4096)  # 4KB buffer
                        await self.process_event(data, addr)
                    except socket.error:
                        # No data available, continue
                        continue
                        
                except Exception as e:
                    logger.error("Error in event listening loop", error=str(e))
                    await asyncio.sleep(1)  # Back off on error
                    
        except Exception as e:
            logger.error("Failed to start OpenSIPS Event Listener", error=str(e))
            raise
    
    async def stop(self):
        """Event listener'ı durdur"""
        try:
            self.running = False
            if self.socket:
                self.socket.close()
                self.socket = None
            
            logger.info("OpenSIPS Event Listener stopped")
            
        except Exception as e:
            logger.error("Error stopping OpenSIPS Event Listener", error=str(e))
    
    async def process_event(self, data: bytes, addr: tuple):
        """
        Gelen event'i işle
        
        Args:
            data: Event data bytes
            addr: Sender address (IP, port)
        """
        try:
            # Event data'yı decode et
            event_str = data.decode('utf-8').strip()
            
            logger.debug("Received event", 
                        data=event_str[:100], 
                        sender=f"{addr[0]}:{addr[1]}")
            
            # Event parsing - OpenSIPS event format
            # Format genellikle: "EVENT_NAME:param1:param2:..."
            parts = event_str.split(':', 1)
            if len(parts) >= 1:
                event_name = parts[0]
                event_data = parts[1] if len(parts) > 1 else ""
                
                await self.handle_event(event_name, event_data, addr)
            else:
                logger.warning("Invalid event format", data=event_str)
                
        except Exception as e:
            logger.error("Error processing event", 
                        error=str(e), 
                        data=data[:100] if data else None)
    
    async def handle_event(self, event_name: str, event_data: str, addr: tuple):
        """
        Event'i uygun handler'a yönlendir
        
        Args:
            event_name: Event adı
            event_data: Event verisi
            addr: Sender address
        """
        try:
            # Handler'ı bul
            handler = self.event_handlers.get(event_name)
            
            if handler:
                await handler(event_data, addr)
            else:
                # Bilinmeyen event - log et
                logger.info("Unknown event received", 
                           event_name=event_name,
                           event_data=event_data[:50],
                           sender=f"{addr[0]}:{addr[1]}")
                
        except Exception as e:
            logger.error("Error handling event", 
                        event_name=event_name,
                        error=str(e))
    
    async def handle_call_event(self, event_data: str, addr: tuple):
        """OAVC call event handler"""
        try:
            # Format: "CALL_START:call_id:from:to" veya "CALL_ESTABLISHED:call_id:status"
            parts = event_data.split(':', 3)
            if len(parts) >= 2:
                sub_event = parts[0]  # CALL_START, CALL_ESTABLISHED, etc.
                call_id = parts[1]
                
                if sub_event == "CALL_START":
                    from_uri = parts[2] if len(parts) > 2 else "unknown"
                    to_uri = parts[3] if len(parts) > 3 else "unknown"
                    
                    logger.info("🔄 New call started", 
                               call_id=call_id,
                               from_uri=from_uri,
                               to_uri=to_uri,
                               timestamp=datetime.now().isoformat())
                    
                elif sub_event == "CALL_ESTABLISHED":
                    status = parts[2] if len(parts) > 2 else "200"
                    
                    logger.info("✅ Call established", 
                               call_id=call_id,
                               status=status,
                               timestamp=datetime.now().isoformat())
                
                else:
                    logger.info("📞 Call event", 
                               sub_event=sub_event,
                               call_id=call_id,
                               data=event_data)
            
        except Exception as e:
            logger.error("Error handling call event", 
                        event_data=event_data,
                        error=str(e))
    
    async def handle_call_setup(self, event_data: str, addr: tuple):
        """Call setup event handler"""
        logger.info("📞 Call setup event", event_data=event_data)
    
    async def handle_call_answered(self, event_data: str, addr: tuple):
        """Call answered event handler"""  
        logger.info("📞 Call answered event", event_data=event_data)
    
    async def handle_call_terminated(self, event_data: str, addr: tuple):
        """Call terminated event handler"""
        logger.info("📞 Call terminated event", event_data=event_data)

class OpenSIPSMIClient:
    """OpenSIPS MI Datagram Client"""
    
    def __init__(self, host: str = "172.20.0.6", port: int = 8087):
        """
        Initialize MI client
        
        Args:
            host: OpenSIPS MI host
            port: OpenSIPS MI port (config'te değiştirildi: 8087)
        """
        self.host = host
        self.port = port
        
        logger.info("OpenSIPS MI Client initialized", 
                   host=host, port=port)
    
    async def send_mi_command(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """
        MI komutu gönder
        
        Args:
            command: MI komutu (örn: "ps", "uptime", "get_statistics")
            timeout: Response timeout
            
        Returns:
            Response string veya None
        """
        try:
            # UDP socket oluştur
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            # Command gönder
            sock.sendto(command.encode('utf-8'), (self.host, self.port))
            
            # Response al
            response, addr = sock.recvfrom(4096)
            sock.close()
            
            response_str = response.decode('utf-8')
            
            logger.info("MI command executed", 
                       command=command,
                       response_size=len(response_str))
            
            return response_str
            
        except Exception as e:
            logger.error("Error sending MI command", 
                        command=command,
                        error=str(e))
            return None
    
    async def get_statistics(self) -> Optional[Dict[str, Any]]:
        """OpenSIPS istatistiklerini al"""
        try:
            response = await self.send_mi_command("get_statistics")
            if response:
                # Response'u parse et (basit implementation)
                stats = {}
                for line in response.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        stats[key.strip()] = value.strip()
                
                return stats
            return None
            
        except Exception as e:
            logger.error("Error getting statistics", error=str(e))
            return None

async def main():
    """Test the event listener"""
    
    # Event listener'ı başlat
    event_listener = OpenSIPSEventListener()
    
    # MI client'ı test et
    mi_client = OpenSIPSMIClient()
    
    try:
        logger.info("🚀 Starting OpenSIPS Event Listener...")
        
        # Event listener task'ı başlat
        listener_task = asyncio.create_task(event_listener.start())
        
        # Test için MI komutları gönder
        await asyncio.sleep(2)
        
        logger.info("📡 Testing MI commands...")
        
        # Test MI commands
        uptime = await mi_client.send_mi_command("uptime")
        if uptime:
            logger.info("OpenSIPS uptime", response=uptime[:100])
        
        stats = await mi_client.get_statistics()
        if stats:
            logger.info("OpenSIPS statistics", count=len(stats))
        
        # Event listener'ı çalıştır
        await listener_task
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        await event_listener.stop()
    except Exception as e:
        logger.error("Error in main", error=str(e))
        await event_listener.stop()

if __name__ == "__main__":
    # Configure structured logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Run the event listener
    asyncio.run(main()) 