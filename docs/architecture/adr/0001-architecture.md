---
adr: 1
title: Arquitetura de Dados Offline-First, Persistência Local com Room e Sincronização Assíncrona
status: Approved
date: 2026-10-10
authors:
  - Josias Sobrinho
  - Márcia Bissaco
impacted_components:
  - directory: app/src/main/java/br/gov/sp/fatec/cupinzeiro/data/
  - component: Room Database & Data Access Objects (DAOs)
  - component: Internal App-Specific Scoped Storage
  - component: Background Sync Engine (WorkManager)
  - component: Export Service (CSV / PDF Exporter)
rules:
  architectural_pattern: "Offline-First Repository Pattern (Android Jetpack + MVVM)"
  persistence:
    engine: "androidx.room:room-runtime"
    sqlite_abstraction: "ORM com validação estática de consultas em tempo de compilação"
    binary_storage: "Path-only reference in SQLite; JPEGs stored in Context.filesDir"
  synchronization:
    scheduler: "androidx.work:work-runtime-ktx"
    network_constraint: "NetworkType.CONNECTED (prioridade para Wi-Fi)"
    battery_constraint: "BatteryNotLow"
    conflict_resolution: "Client-Wins com UUID v4 e Timestamp UTC imutável"
  local_fallback:
    export_formats:
      - CSV
      - JSON
      - PDF
---

# ADR 001: Arquitetura de Dados Offline-First, Persistência Local com Room e Sincronização em Campo

## Status
Aprovado (2026-10-10)

## Contexto
O monitoramento e mensuração métrica de cupinzeiros de montículo (*Cornitermes cumulans*) ocorrem fisicamente em pastagens e áreas rurais remotas, onde o sinal de conectividade de dados celulares (3G/4G/5G) é inexistente ou altamente instável. Uma arquitetura de software orientada a serviços remotos síncronos (*Cloud-First* ou *API-First*) tornaria o aplicativo inoperável no campo, gerando travamentos de interface (*ANR - Application Not Responding*), perda de medições e frustração operacional para o produtor rural.

Adicionalmente, cada medição biométrica envolve a captura e geração de evidências fotográficas de alta resolução (a foto original da pastagem e a imagem processada com o HUD métrico do OpenCV). Armazenar arquivos de imagem pesados como objetos binários grandes (*BLOBs*) diretamente no banco de dados relacional causaria inchaço rápido (*database bloat*), esgotamento de memória RAM durante consultas e severa degradação de I/O no dispositivo móvel.

Portanto, era imperativo definir:
1. Uma estratégia de persistência que garanta **autonomia operacional 100% offline** durante a jornada de campo;
2. Uma separação limpa entre metadados tabulares e arquivos binários de mídia;
3. Um mecanismo resiliente para consolidação e exportação dos dados coletados (sincronização em nuvem e exportação local).

## Decisão
Adotamos uma **Arquitetura de Dados Offline-First com Android Jetpack Room, Armazenamento Híbrido de Mídia e Sincronização Assíncrona via WorkManager**:

### 1. Padrão Offline-First como Fonte Primária da Verdade (*Single Source of Truth*)
* A interface do usuário (UI / ViewModel) consome dados exclusivamente do repositório local, que tem como fonte primária a **Room Persistence Library** (ORM oficial do Android Jetpack sobre SQLite).
* O aplicativo não depende de respostas HTTP síncronas para habilitar ações de usuário: medições, cálculos métricos com ArUco, estimativas volumétricas e cadastros de fazendas/piquetes são persistidos localmente de forma instantânea.
* As consultas do Room retornam fluxos reativos nativos (`Flow` / `StateFlow` em Kotlin), garantindo que qualquer inserção ou alteração de status reflita reativamente na interface sem necessidade de polling manual.

### 2. Estratégia Híbrida de Armazenamento de Imagens (*Path-Only Reference*)
* **Segregação Estrita de Binários:** Nenhuma imagem é gravada dentro do banco de dados SQLite.
* **Armazenamento no Sistema de Arquivos Seguro:** As imagens capturadas da câmera e as imagens processadas com as anotações do OpenCV são salvas no armazenamento interno privativo do aplicativo (`context.filesDir` / Scoped Storage). Esse diretório é inacessível para outros aplicativos por padrão e não polui a galeria pública do produtor.
* **Referenciação Métrica:** O banco de dados armazena apenas strings contendo os caminhos canônicos locais (`path_foto_original` e `path_foto_processada`), mantendo o banco extremamente leve (< 50 KB para centenas de medições).

### 3. Modelagem de Entidade Local (Schema Room)
A tabela `medicoes_cupinzeiro` foi projetada para manter a rastreabilidade agronômica, fotométrica e métrica das estruturas:

```kotlin
@Entity(tableName = "medicoes_cupinzeiro")
data class MedicaoCupinzeiroEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    
    // Identificação Territorial e Temporal
    @ColumnInfo(name = "uuid_registro") val uuidRegistro: String = UUID.randomUUID().toString(),
    @ColumnInfo(name = "fazenda_nome") val fazendaNome: String,
    @ColumnInfo(name = "piquete_identificador") val piqueteIdentificador: String,
    @ColumnInfo(name = "data_hora_coleta") val dataHoraColeta: Long = System.currentTimeMillis(),
    @ColumnInfo(name = "latitude") val latitude: Double?,
    @ColumnInfo(name = "longitude") val longitude: Double?,
    
    // Métricas Físicas Estimadas via OpenCV
    @ColumnInfo(name = "largura_cm") val larguraCm: Double,
    @ColumnInfo(name = "altura_cm") val alturaCm: Double,
    @ColumnInfo(name = "area_frontal_cm2") val areaFrontalCm2: Double,
    @ColumnInfo(name = "volume_estimado_litros") val volumeEstimadoLitros: Double,
    @ColumnInfo(name = "fator_escala_cm_px") val fatorEscalaCmPx: Double,
    
    // Controle Fiduciário e Qualidade da Medição
    @ColumnInfo(name = "aruco_detectado") val arucoDetectado: Boolean,
    @ColumnInfo(name = "angulo_inclinacao_graus") val anguloInclinacaoGraus: Double,
    
    // Referências no Sistema de Arquivos
    @ColumnInfo(name = "path_foto_original") val pathFotoOriginal: String,
    @ColumnInfo(name = "path_foto_processada") val pathFotoProcessada: String,
    
    // Ciclo de Vida e Sincronização
    @ColumnInfo(name = "status_sincronizacao") val statusSincronizacao: SyncStatus = SyncStatus.PENDENTE,
    @ColumnInfo(name = "sincronizado_em") val sincronizadoEm: Long? = null
)

enum class SyncStatus {
    PENDENTE,
    EM_PROGRESSO,
    SINCRONIZADO,
    FALHA
}
```

### 4. Mecanismo de Sincronização Dupla (Nuvem Automática + Exportação Local)
Para atender tanto o produtor rural tecnificado quanto o pecuarista sem infraestrutura em nuvem, o sistema adota um modelo de sincronização dupla:

1. **Sincronização em Nuvem em Segundo Plano (WorkManager):**
   - Um worker assíncrono (`SyncMedicoesWorker : CoroutineWorker`) é escalonado via **Android Jetpack WorkManager**.
   - **Critérios de Ativação (*Constraints*):** Conexão de rede ativa (`NetworkType.CONNECTED`, priorizando Wi-Fi não tarifada) e bateria suficiente (`BatteryNotLow`).
   - Quando o dispositivo detecta internet (ex.: ao retornar à sede da fazenda no final da tarde), o worker faz o upload em lotes (*batch upload*) via API REST (Retrofit), enviando os dados JSON e as imagens compactadas multipart, atualizando o `status_sincronizacao` para `SINCRONIZADO`.

2. **Exportação Local Offline Direta (Fallback Operacional):**
   - Independentemente de conexão com a internet ou existência de servidor em nuvem, o aplicativo oferece um serviço de exportação local de laudos agronômicos.
   - Gera relatórios consolidados em **CSV / Excel** e **PDF**, disponibilizados via `FileProvider` do Android para envio imediato via Bluetooth, pendrive OTG, WhatsApp ou e-mail quando houver conectividade pontual.

## Consequências

### Positivas (Prós)
* **Autonomia Absoluta em Campo:** O operador realiza medições e análises métricas ilimitadas em áreas remotas sem qualquer dependência de conectividade.
* **Desempenho e Resposta Imediata:** Leituras e gravações na memória interna e no Room ocorrem em microssegundos, eliminando bloqueios de interface e telas de espera.
* **Eficiência Energética Crítica:** Ao suprimir chamadas contínuas de rádio celular (que consomem alto nível de bateria ao tentar se conectar a torres distantes em áreas rurais), a autonomia da bateria do aparelho é preservada durante toda a jornada de trabalho.
* **Segurança e Escalabilidade de Armazenamento:** A abordagem *path-only* impede o inchaço do SQLite, mantendo o banco leve e estável independentemente do volume de fotos coletadas.
* **Segurança de Tipos e Validação em Compilação:** O Room assegura validação estática de instruções SQL no momento da compilação do projeto em Kotlin, prevenindo falhas de runtime comuns no SQLite bruto.

### Negativas (Contras) e Mitigações
* **Risco de Perda de Dados se o Aparelho for Danificado:** Se o smartphone for avariado antes do upload ou exportação, medições locais não sincronizadas podem ser perdidas.
  - *Mitigação:* Alerta visual no cabeçalho do aplicativo exibindo o quantitativo de medições pendentes e incentivo à exportação rápida em arquivo CSV ao final de cada piquete.
* **Acúmulo de Imagens no Armazenamento Interno do Dispositivo:** Coletas contínuas ao longo de meses podem comprometer o espaço em disco do celular.
  - *Mitigação:* Política de retenção gerenciada: após confirmação de sincronização na nuvem (`SyncStatus.SINCRONIZADO`), o aplicativo disponibiliza recurso para expurgar imagens brutas antigas, retendo os metadados tabulares e miniaturas compactadas (*thumbnails*).
* **Tratamento de Conflitos em Dispositivos Múltiplos:** Caso mais de um técnico meça o mesmo piquete simultaneamente.
  - *Mitigação:* Chaves de identificação únicas universais (`uuid_registro` UUID v4) e política aditiva *Client-Wins* baseada em timestamp UTC imutável de criação no campo.
