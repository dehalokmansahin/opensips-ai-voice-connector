# Architectural Cleanup Plan - OpenSIPS AI Voice Connector

**Date:** 2025-07-27  
**Status:** CRITICAL - Immediate Action Required  
**Phase:** 2.5 - Pre-Phase 3 Cleanup  

## Executive Summary

Critical architectural inconsistencies and incomplete implementations have been identified that must be resolved before proceeding with Phase 3. This cleanup is essential for system stability and MVP delivery.

## Critical Issues Identified

### 1. 🔄 **Legacy-New Architecture Conflict**
**Priority:** CRITICAL  
**Impact:** System confusion, resource waste, maintenance complexity

**Current State:**
- Dual architecture: `src/` (legacy) vs `core/` (new)
- `src/opensips_bot.py` conflicts with `core/main.py`
- Unclear system boundaries and entry points

**Resolution Required:**
- [ ] Remove entire `src/` directory 
- [ ] Commit fully to `core/` architecture
- [ ] Update all references and documentation
- [ ] Archive legacy code in separate branch if needed

### 2. ⚠️ **Incomplete Pipecat Integration**
**Priority:** HIGH  
**Impact:** Core audio pipeline functionality missing

**Current State:**
- `core/pipecat/` contains only wrapper classes
- No real pipeline orchestration implementation
- Missing audio frame processing logic

**Resolution Required:**
- [ ] Complete `core/pipecat/pipeline/pipeline.py` implementation
- [ ] Implement audio frame processing in `core/pipecat/frames/frames.py`
- [ ] Add processor implementations in `core/pipecat/processors/`
- [ ] Integrate with service clients

### 3. 🔗 **Service Discovery Conflicts**
**Priority:** HIGH  
**Impact:** Service communication instability

**Current State:**
- Two service registry patterns in use:
  - `core/grpc_clients/service_registry.py`
  - `services/common/service_base.py`
- Conflicting service discovery approaches

**Resolution Required:**
- [ ] Unify service discovery pattern
- [ ] Choose one registry implementation
- [ ] Update all services to use unified approach
- [ ] Remove duplicate service registry code

### 4. 📂 **gRPC Proto Organization Issues**
**Priority:** MEDIUM  
**Impact:** Development velocity reduction

**Current State:**
- Proto files scattered:
  - `services/asr-service/proto/`
  - `services/llm-service/proto/`
  - `services/tts-service/proto/`
  - `shared/proto/`

**Resolution Required:**
- [ ] Centralize all proto definitions in `shared/proto/`
- [ ] Create unified code generation script
- [ ] Update service imports
- [ ] Implement versioning strategy

### 5. 🔌 **OpenSIPS Integration Incomplete**
**Priority:** CRITICAL  
**Impact:** MVP blocker - no telephony functionality

**Current State:**
- `core/opensips/integration.py` is placeholder
- `core/opensips/rtp_transport.py` incomplete
- No SIP signaling implementation

**Resolution Required:**
- [ ] Implement basic SIP signaling in `integration.py`
- [ ] Complete RTP transport implementation
- [ ] Add OpenSIPS event handling
- [ ] Integrate with pipeline manager

## Cleanup Implementation Plan

### Phase 2.5.1: Architecture Consolidation (Week 1)
1. **Legacy Removal**
   - Archive `src/` directory
   - Remove all legacy references
   - Update Docker configurations

2. **Service Registry Unification**
   - Choose core service registry pattern
   - Refactor all services
   - Test service discovery

### Phase 2.5.2: Core Implementation (Week 2)
1. **Pipecat Integration**
   - Complete pipeline implementation
   - Add audio processing
   - Test with mock data

2. **Proto Organization**
   - Centralize proto definitions
   - Update build scripts
   - Test code generation

### Phase 2.5.3: OpenSIPS Foundation (Week 3)
1. **Basic SIP Implementation**
   - Implement SIP signaling
   - Add RTP transport
   - Test with softphone

2. **Integration Testing**
   - End-to-end audio flow
   - Service coordination
   - Performance validation

## Success Criteria

### Technical Validation
- [ ] Single architecture with no legacy conflicts
- [ ] Working Pipecat pipeline with audio processing
- [ ] Unified service discovery across all services
- [ ] Centralized proto management with versioning
- [ ] Basic SIP/RTP functionality operational

### Performance Targets
- [ ] Service startup time < 30 seconds
- [ ] Inter-service communication latency < 50ms
- [ ] Audio pipeline latency < 200ms
- [ ] Memory usage stable under load

### Quality Gates
- [ ] All architectural conflicts resolved
- [ ] No duplicate or conflicting code patterns
- [ ] Comprehensive test coverage for new implementations
- [ ] Documentation updated to reflect current architecture

## Risk Mitigation

### High Risk Areas
1. **Service Discovery Changes** - May break existing functionality
   - Mitigation: Incremental rollout with fallback
   
2. **Pipecat Integration** - Complex audio processing
   - Mitigation: Extensive testing with mock data first
   
3. **OpenSIPS Implementation** - Critical path item
   - Mitigation: Start with minimal viable implementation

### Rollback Plan
- Maintain tagged releases at each phase
- Document rollback procedures
- Keep legacy branch available for emergency fallback

## Resource Requirements

### Development Time
- **Phase 2.5.1:** 1 week (Architecture cleanup)
- **Phase 2.5.2:** 1 week (Core implementation)  
- **Phase 2.5.3:** 1 week (OpenSIPS foundation)
- **Total:** 3 weeks before Phase 3 can begin

### Testing Requirements
- Unit tests for all new implementations
- Integration tests for service coordination
- Performance testing for audio pipeline
- End-to-end testing with SIP client

## Next Steps

1. **Immediate (Today):**
   - Approve this cleanup plan
   - Begin legacy code archival
   - Start service registry unification

2. **Week 1:**
   - Complete architecture consolidation
   - Test unified service discovery

3. **Week 2:**
   - Implement core Pipecat integration
   - Centralize proto organization

4. **Week 3:**
   - Build OpenSIPS foundation
   - Validate end-to-end functionality

5. **Week 4:**
   - Final integration testing
   - Documentation updates
   - Ready for Phase 3

## Conclusion

This architectural cleanup is essential for project success. The identified issues represent technical debt that will severely impact development velocity and system reliability if not addressed immediately. 

Completing this cleanup will provide:
- Clear, maintainable architecture
- Solid foundation for Phase 3 development
- Reduced complexity and confusion
- Better performance and reliability

**Recommendation:** Proceed with this cleanup plan immediately before any further Phase 3 development.