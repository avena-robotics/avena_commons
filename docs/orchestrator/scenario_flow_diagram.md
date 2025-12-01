# AI-generated documentation: Scenario flow diagram conversion guide and formats for orchestrator architecture visualization.

# Diagramy przepływu scenariusza - opcje konwersji

## 1. Format draw.io (XML)

Aby utworzyć diagram w draw.io:

1. Otwórz https://app.diagrams.net/
2. Wybierz "Create New Diagram"
3. Importuj poniższy kod XML lub narysuj ręcznie:

```xml
<mxfile host="app.diagrams.net" modified="2025-01-01T00:00:00.000Z" agent="AI Assistant" etag="ScenarioFlow" version="24.7.17">
  <diagram name="Scenario Flow" id="scenario-orchestrator-flow">
    <mxGraphModel dx="1680" dy="980" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1200" pageHeight="1600" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        
        <!-- Główny przepływ scenariusza -->
        <mxCell id="start" value="START&#xa;Trigger scenariusza" style="ellipse;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontStyle=1;fontSize=12;" vertex="1" parent="1">
          <mxGeometry x="100" y="40" width="140" height="70" as="geometry"/>
        </mxCell>
        
        <mxCell id="loadScenario" value="Ładowanie definicji scenariusza z YAML" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="90" y="150" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="validateConditions" value="Ewaluacja warunków&lt;br&gt;(conditions)" style="rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;" vertex="1" parent="1">
          <mxGeometry x="110" y="240" width="120" height="100" as="geometry"/>
        </mxCell>
        
        <mxCell id="createContext" value="Utworzenie ScenarioContext" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="350" y="265" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="mergeClientData" value="Łączenie danych klientów&lt;br&gt;(config + state)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="350" y="360" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="actionLoop" value="Iteracja przez&lt;br&gt;listę akcji" style="hexagon;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontStyle=1;" vertex="1" parent="1">
          <mxGeometry x="370" y="460" width="120" height="60" as="geometry"/>
        </mxCell>
        
        <mxCell id="templateResolution" value="Rozwiązywanie&lt;br&gt;szablonów w konfiguracji akcji" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="350" y="570" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="executeAction" value="Wykonanie akcji&lt;br&gt;(BaseAction.execute)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;" vertex="1" parent="1">
          <mxGeometry x="350" y="670" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="actionResult" value="Przetworzenie&lt;br&gt;wyniku akcji" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="350" y="770" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="moreActions" value="Więcej akcji?" style="rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="370" y="870" width="120" height="80" as="geometry"/>
        </mxCell>
        
        <mxCell id="cleanup" value="Czyszczenie kontekstu&lt;br&gt;scenariusza" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;" vertex="1" parent="1">
          <mxGeometry x="350" y="1000" width="160" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="end" value="KONIEC&lt;br&gt;Zwrot wyniku" style="ellipse;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontStyle=1;fontSize=12;" vertex="1" parent="1">
          <mxGeometry x="360" y="1100" width="140" height="70" as="geometry"/>
        </mxCell>
        
        <mxCell id="conditionsFailed" value="KONIEC&lt;br&gt;Warunki niespełnione" style="ellipse;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontStyle=1;" vertex="1" parent="1">
          <mxGeometry x="100" y="400" width="140" height="70" as="geometry"/>
        </mxCell>
        
        <!-- Template Resolution Engine (subgraf) -->
        <mxCell id="templateEngineGroup" value="" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;dashed=1;strokeWidth=2;" vertex="1" parent="1">
          <mxGeometry x="600" y="520" width="320" height="280" as="geometry"/>
        </mxCell>
        
        <mxCell id="templateEngineLabel" value="Template Resolution Engine" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontStyle=1;fontSize=14;" vertex="1" parent="1">
          <mxGeometry x="650" y="530" width="220" height="30" as="geometry"/>
        </mxCell>
        
        <mxCell id="templateInput" value="Wartość z konfiguracji" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;" vertex="1" parent="1">
          <mxGeometry x="680" y="570" width="120" height="40" as="geometry"/>
        </mxCell>
        
        <mxCell id="templateCheck" value="Czy pojedyncza&lt;br&gt;zmienna {{ var }}?" style="rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="680" y="630" width="120" height="80" as="geometry"/>
        </mxCell>
        
        <mxCell id="templatePreserveType" value="Zachowaj&lt;br&gt;oryginalny typ" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="620" y="740" width="80" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="templateRenderString" value="Renderuj&lt;br&gt;jako string" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="760" y="740" width="80" height="50" as="geometry"/>
        </mxCell>
        
        <!-- Unified Client Data (subgraf) -->
        <mxCell id="clientDataGroup" value="" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;dashed=1;strokeWidth=2;" vertex="1" parent="1">
          <mxGeometry x="600" y="120" width="320" height="220" as="geometry"/>
        </mxCell>
        
        <mxCell id="clientDataLabel" value="Unified Client Data" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontStyle=1;fontSize=14;" vertex="1" parent="1">
          <mxGeometry x="680" y="130" width="160" height="30" as="geometry"/>
        </mxCell>
        
        <mxCell id="clientConfig" value="Konfiguracja klienta&lt;br&gt;(address, port)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="620" y="170" width="100" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="clientState" value="Stan aktualny&lt;br&gt;(fsm_state, error)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="780" y="170" width="100" height="50" as="geometry"/>
        </mxCell>
        
        <mxCell id="clientMerged" value="Połączone dane klienta" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="700" y="250" width="120" height="40" as="geometry"/>
        </mxCell>
        
        <mxCell id="clientAccess" value="context.clients[name]" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontStyle=2;" vertex="1" parent="1">
          <mxGeometry x="700" y="310" width="120" height="30" as="geometry"/>
        </mxCell>
        
        <!-- Główne strzałki przepływu -->
        <mxCell id="arrow1" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#e1d5e7;strokeColor=#9673a6;" edge="1" parent="1" source="start" target="loadScenario">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#d5e8d4;strokeColor=#82b366;" edge="1" parent="1" source="loadScenario" target="validateConditions">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#d5e8d4;strokeColor=#82b366;" edge="1" parent="1" source="validateConditions" target="createContext">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow3_label" value="SPEŁNIONE" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontStyle=1;fillColor=#ffffff;" vertex="1" connectable="0" parent="arrow3">
          <mxGeometry x="-0.2" y="-2" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <mxCell id="arrow4" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#f8cecc;strokeColor=#b85450;" edge="1" parent="1" source="validateConditions" target="conditionsFailed">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow4_label" value="NIESPEŁNIONE" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontStyle=1;fillColor=#ffffff;" vertex="1" connectable="0" parent="arrow4">
          <mxGeometry x="-0.1" y="-1" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <mxCell id="arrow5" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#d5e8d4;strokeColor=#82b366;" edge="1" parent="1" source="createContext" target="mergeClientData">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow6" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#f8cecc;strokeColor=#b85450;" edge="1" parent="1" source="mergeClientData" target="actionLoop">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow7" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#dae8fc;strokeColor=#6c8ebf;" edge="1" parent="1" source="actionLoop" target="templateResolution">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow8" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#dae8fc;strokeColor=#6c8ebf;" edge="1" parent="1" source="templateResolution" target="executeAction">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow9" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#dae8fc;strokeColor=#6c8ebf;" edge="1" parent="1" source="executeAction" target="actionResult">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow10" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#fff2cc;strokeColor=#d6b656;" edge="1" parent="1" source="actionResult" target="moreActions">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow11" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#f8cecc;strokeColor=#b85450;" edge="1" parent="1" source="moreActions" target="cleanup">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="arrow11_label" value="NIE" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontStyle=1;fillColor=#ffffff;" vertex="1" connectable="0" parent="arrow11">
          <mxGeometry x="-0.1" y="-1" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <mxCell id="arrow12" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#e1d5e7;strokeColor=#9673a6;" edge="1" parent="1" source="cleanup" target="end">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <!-- Pętla powrotu do następnej akcji -->
        <mxCell id="arrow13" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;fillColor=#fff2cc;strokeColor=#d6b656;" edge="1" parent="1" source="moreActions" target="actionLoop">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="280" y="910"/>
              <mxPoint x="280" y="490"/>
            </Array>
          </mxGeometry>
        </mxCell>
        
        <mxCell id="arrow13_label" value="TAK" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontStyle=1;fillColor=#ffffff;" vertex="1" connectable="0" parent="arrow13">
          <mxGeometry x="-0.8" y="-1" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <!-- Strzałki Template Resolution Engine -->
        <mxCell id="template_arrow1" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;dashed=1;" edge="1" parent="1" source="templateResolution" target="templateInput">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="template_arrow2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="templateInput" target="templateCheck">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="template_arrow3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="templateCheck" target="templatePreserveType">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="template_arrow3_label" value="TAK" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontSize=10;" vertex="1" connectable="0" parent="template_arrow3">
          <mxGeometry x="-0.1" y="-1" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <mxCell id="template_arrow4" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="templateCheck" target="templateRenderString">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="template_arrow4_label" value="NIE" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontSize=10;" vertex="1" connectable="0" parent="template_arrow4">
          <mxGeometry x="-0.1" y="-1" relative="1" as="geometry">
            <mxPoint as="offset"/>
          </mxGeometry>
        </mxCell>
        
        <!-- Strzałki Client Data -->
        <mxCell id="client_arrow1" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;dashed=1;" edge="1" parent="1" source="mergeClientData" target="clientConfig">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="client_arrow2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="clientConfig" target="clientMerged">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="client_arrow3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="clientState" target="clientMerged">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="client_arrow4" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1;" edge="1" parent="1" source="clientMerged" target="clientAccess">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## 2. Format PlantUML

```plantuml
@startuml Scenario Flow

start
:Trigger scenariusza;
if (Walidacja warunków?) then (Spełnione)
  :Budowa ScenarioContext;
  :Łączenie danych klientów;
  note right
    Config + State
  end note
  :Rozwiązywanie szablonów;
  note right
    Zachowane typy
  end note
  :Wykonanie akcji;
  :Akcja z pełnym kontekstem;
  :Kolejna akcja;
  :Czyszczenie kontekstu;
else (Niespełnione)
endif
stop

note as N1
  **Template Resolution Engine**
  if (Czy pojedyncza zmienna?) then (Tak)
    :Zachowaj oryginalny typ;
    :Zwróć wartość;
  else (Nie)
    :Renderuj jako string;
    :Zwróć string;
  endif
end note

note as N2
  **Unified Client Data**
  :Konfiguracja klienta| + |Stan aktualny;
  :Połączone dane;
  :context.clients[name];
end note

@enduml
```

## 3. Format Lucidchart

Kroki do utworzenia w Lucidchart:
1. Zaloguj się do https://lucidchart.com
2. Utwórz nowy diagram typu "Flowchart"
3. Użyj kształtów:
   - **Owale** dla Start/End (Trigger, Koniec)
   - **Romby** dla decyzji (Walidacja warunków, Czy pojedyncza zmienna?)
   - **Prostokąty** dla procesów
   - **Grupowanie** dla subgrafów

## 4. Format ASCII Art

```
┌─────────────────┐
│ Trigger         │
│ scenariusza     │
└─────────┬───────┘
          │
          ▼
     ┌────────────┐      ┌─────────────┐
     │ Walidacja  │ YES  │   Budowa    │
     │ warunków?  ├─────▶│ScenarioCtx  │
     └────┬───────┘      └─────┬───────┘
          │ NO                 │
          ▼                    ▼
     ┌─────────┐         ┌─────────────┐
     │ Koniec  │         │ Łączenie    │
     └─────────┘         │ danych      │
                         │ klientów    │
                         └─────┬───────┘
                               │
                               ▼
                         ┌─────────────┐
                         │Rozwiązywanie│
                         │ szablonów   │
                         └─────┬───────┘
                               │
                               ▼
                         ┌─────────────┐
                         │ Wykonanie   │
                         │ akcji       │
                         └─────┬───────┘
                               │
                               ▼
                         ┌─────────────┐
                         │ Czyszczenie │
                         │ kontekstu   │
                         └─────┬───────┘
                               │
                               ▼
                         ┌─────────────┐
                         │   Koniec    │
                         └─────────────┘

╔═══════════════════════════════════╗
║      Template Resolution Engine   ║
╠═══════════════════════════════════╣
║  ┌─────────────────┐              ║
║  │ Czy pojedyncza  │              ║
║  │ zmienna?        │              ║
║  └─────┬───────────┘              ║
║        │ TAK    │ NIE              ║
║        ▼        ▼                 ║
║  ┌─────────┐ ┌─────────────┐      ║
║  │Zachowaj │ │ Renderuj    │      ║
║  │typ orig.│ │ jako string │      ║
║  └─────────┘ └─────────────┘      ║
╚═══════════════════════════════════╝
```

## 5. Konwersja z Mermaid

Aby przekonwertować istniejący kod Mermaid:

### Online narzędzia:
- **Mermaid Live Editor**: https://mermaid-js.github.io/mermaid-live-editor/
- **Draw.io**: Importuj Mermaid bezpośrednio
- **Kroki**: File → Import → Text → wklej kod Mermaid

### VS Code Extensions:
- **Mermaid Preview**: podgląd w edytorze
- **Draw.io Integration**: edycja diagramów w VS Code

### Programatyczne konwersje:
```bash
# Za pomocą mermaid-cli
npm install -g @mermaid-js/mermaid-cli
mmdc -i diagram.mmd -o diagram.png
mmdc -i diagram.mmd -o diagram.svg
```

## Zalecenia

**Dla dokumentacji technicznej**: PlantUML lub Mermaid (łatwa edycja w markdown)
**Dla prezentacji**: draw.io lub Lucidchart (lepsze formatowanie wizualne)
**Dla prostych diagramów**: ASCII art w dokumentacji tekstowej
**Dla złożonych workflow**: draw.io z możliwością eksportu do różnych formatów

Mermaid diagram można łatwo osadzić w markdown i będzie renderowany na GitHub, GitLab i większości platform dokumentacyjnych.