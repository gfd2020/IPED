package iped.app.graph;

import java.awt.BorderLayout;
import java.awt.Desktop;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import javax.swing.event.AncestorListener;
import javax.swing.event.AncestorEvent;

import java.util.Map;

import java.util.HashMap;
import netscape.javascript.JSObject;
import java.awt.Component;
import java.awt.Font;
import javax.swing.Box;
import javax.swing.BoxLayout;
import javax.swing.JLabel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingConstants;

import javax.swing.JButton;
import javax.swing.JPanel;
import javax.swing.JToolBar;
import javax.swing.SwingWorker;

import org.neo4j.graphdb.GraphDatabaseService;
import org.neo4j.graphdb.Node;
import org.neo4j.graphdb.Relationship;
import org.neo4j.graphdb.Result;
import org.neo4j.graphdb.Transaction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import iped.app.ui.Messages;
import iped.engine.graph.GraphService;
import iped.engine.graph.GraphServiceFactoryImpl;
import javafx.application.Platform;
import javafx.embed.swing.JFXPanel;
import javafx.scene.Scene;
import javafx.scene.layout.StackPane;
import javafx.scene.web.WebEngine;
import javafx.scene.web.WebView;

/**
 * Panel that displays fiscal transaction graph using vis.js in a WebView.
 */
public class FiscalGraphPanel extends JPanel {

    private static final long serialVersionUID = 1L;
    private static final Logger LOGGER = LoggerFactory.getLogger(FiscalGraphPanel.class);

    // Initial SVG provided by user
    private static final String COMPANY_SVG_RAW = "<svg version=\"1.1\" xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" x=\"0px\" y=\"0px\" viewBox=\"0 0 256 256\" enable-background=\"new 0 0 256 256\" xml:space=\"preserve\"><g><g><path fill=\"#000000\" d=\"M22.3,246v-9.8h211.4v9.8H22.3 M174.7,231.2h-24.6L150,104.9l-29.4-21.2l-68.8,29.5v118H22.3v-9.8H42V108.3l78.7-34.4l39.3,29.5v118h14.8V231.2z M66.3,128.6l34.6-15.3v19.7l-34.4,14.8L66.3,128.6L66.3,128.6z M101,157.5v19.7L66.5,187l-0.2-18.6L101,157.5z M66.5,206.7l34.4-9.8v24.6H66.5V206.7z M184.5,34.6v196.7h14.7V52L184.5,34.6z M120.6,98.5v132.7h14.7V108.3L120.6,98.5z M233.7,231.2h-24.6V49.3l-24.6-29.5L91.1,59.2v14.8l-9.9,9.8V54.2L189.5,10L219,49.3v172.1h14.8V231.2z\"/></g></g></svg>";
    private static String COMPANY_ICON_SVG_DATA;

    static {
        try {
            String base64Svg = Base64.getEncoder().encodeToString(COMPANY_SVG_RAW.getBytes(StandardCharsets.UTF_8));
            COMPANY_ICON_SVG_DATA = "data:image/svg+xml;base64," + base64Svg;
        } catch (Exception e) {
            LOGGER.error("Error encoding SVG", e);
            COMPANY_ICON_SVG_DATA = "";
        }
    }

    private static final Map<String, String> STATE_COLORS = new HashMap<>();
    static {
        STATE_COLORS.put("AC", "#EF9A9A");
        STATE_COLORS.put("AL", "#F48FB1");
        STATE_COLORS.put("AP", "#CE93D8");
        STATE_COLORS.put("AM", "#B39DDB");
        STATE_COLORS.put("BA", "#9FA8DA");
        STATE_COLORS.put("CE", "#90CAF9");
        STATE_COLORS.put("DF", "#81D4FA");
        STATE_COLORS.put("ES", "#80DEEA");
        STATE_COLORS.put("GO", "#80CBC4");
        STATE_COLORS.put("MA", "#A5D6A7");
        STATE_COLORS.put("MT", "#C5E1A5");
        STATE_COLORS.put("MS", "#E6EE9C");
        STATE_COLORS.put("MG", "#FFF59D");
        STATE_COLORS.put("PA", "#FFE082");
        STATE_COLORS.put("PB", "#FFCC80");
        STATE_COLORS.put("PR", "#FFAB91");
        STATE_COLORS.put("PE", "#BCAAA4");
        STATE_COLORS.put("PI", "#EEEEEE");
        STATE_COLORS.put("RJ", "#B0BEC5");
        STATE_COLORS.put("RN", "#EF9A9A");
        STATE_COLORS.put("RS", "#F48FB1");
        STATE_COLORS.put("RO", "#CE93D8");
        STATE_COLORS.put("RR", "#B39DDB");
        STATE_COLORS.put("SC", "#9FA8DA");
        STATE_COLORS.put("SP", "#90CAF9");
        STATE_COLORS.put("SE", "#81D4FA");
        STATE_COLORS.put("TO", "#80DEEA");
    }

    private JFXPanel jfxPanel;
    private WebView webView;
    private WebEngine webEngine;
    private JButton openInBrowserButton;
    private JButton refreshButton;
    private volatile String currentHtml;
    private volatile File tempHtmlFile;
    private JTextArea detailsArea;
    private JavaBridge javaBridge;
    private String globalStatsText = "";

    public FiscalGraphPanel() {
        setLayout(new BorderLayout());

        // Toolbar
        JToolBar toolbar = new JToolBar();
        toolbar.setFloatable(false);

        refreshButton = new JButton(Messages.getString("FiscalGraphPanel.Refresh"));
        refreshButton.addActionListener(e -> loadFiscalData());
        toolbar.add(refreshButton);

        openInBrowserButton = new JButton(Messages.getString("FiscalGraphPanel.OpenInBrowser"));
        openInBrowserButton.setEnabled(false);
        openInBrowserButton.addActionListener(e -> openInBrowser());
        toolbar.add(openInBrowserButton);

        // Toolbar
        add(toolbar, BorderLayout.NORTH);

        // WebView panel
        Platform.setImplicitExit(false);
        jfxPanel = new JFXPanel();

        Platform.runLater(() -> {
            webView = new WebView();
            webEngine = webView.getEngine();

            StackPane root = new StackPane();
            root.getChildren().add(webView);

            // Initialize bridge
            javaBridge = new JavaBridge(detailsArea);

            // Inject Java bridge when page loads
            webEngine.getLoadWorker().stateProperty().addListener((obs, oldState, newState) -> {
                if (newState == javafx.concurrent.Worker.State.SUCCEEDED) {
                    JSObject win = (JSObject) webEngine.executeScript("window");
                    win.setMember("java", javaBridge);
                }
            });

            Scene scene = new Scene(root);
            jfxPanel.setScene(scene);

            // Load initial empty state
            webEngine.loadContent(getEmptyHtml());
        });

        add(jfxPanel, BorderLayout.CENTER);

        detailsArea = new JTextArea(4, 20);
        detailsArea.setEditable(false);
        add(new JScrollPane(detailsArea), BorderLayout.SOUTH);

        // Auto-load data when panel is added to UI
        addAncestorListener(new AncestorListener() {
            @Override
            public void ancestorAdded(AncestorEvent event) {
                if (currentHtml == null || currentHtml.equals(getEmptyHtml())) {
                    loadFiscalData();
                }
            }

            @Override
            public void ancestorRemoved(AncestorEvent event) {
            }

            @Override
            public void ancestorMoved(AncestorEvent event) {
            }
        });
    }

    /**
     * Load fiscal data from Neo4j and display in the graph.
     */
    public void loadFiscalData() {
        new LoadFiscalDataWorker().execute();
    }

    private void openInBrowser() {
        if (currentHtml == null) {
            return;
        }
        try {
            if (tempHtmlFile == null || !tempHtmlFile.exists()) {
                tempHtmlFile = File.createTempFile("fiscal_graph_", ".html");
                tempHtmlFile.deleteOnExit();
            }
            Files.write(tempHtmlFile.toPath(), currentHtml.getBytes(StandardCharsets.UTF_8));
            Desktop.getDesktop().browse(tempHtmlFile.toURI());
        } catch (IOException e) {
            LOGGER.error("Error opening in browser", e);
        }
    }

    private String getEmptyHtml() {
        return "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>"
                + "<div style='display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;color:#666;'>"
                + Messages.getString("FiscalGraphPanel.Loading")
                + "</div></body></html>";
    }

    private String generateGraphHtml(List<FiscalNode> nodes, List<FiscalEdge> edges) {
        StringBuilder sb = new StringBuilder();
        sb.append("<!DOCTYPE html>\n");
        sb.append("<html>\n<head>\n");
        sb.append("<meta charset='UTF-8'>\n");
        sb.append("<title>Fiscal Graph</title>\n");
        // Load local JS for offline support
        String visJs = "";
        try (java.io.InputStream is = getClass().getResourceAsStream("/js/vis-network.min.js")) {
            if (is != null) {
                visJs = new String(is.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            } else {
                // Fallback or log
            }
        } catch (Exception e) {
            // Log error
        }

        if (visJs.isEmpty()) {
            sb.append("<script src='https://unpkg.com/vis-network/standalone/umd/vis-network.min.js'></script>\n");
        } else {
            sb.append("<script>\n");
            sb.append(visJs);
            sb.append("\n</script>\n");
        }
        sb.append("<style>\n");
        sb.append("  html, body { margin: 0; padding: 0; width: 100%; height: 100%; }\n");
        sb.append("  #graph { width: 100%; height: 100%; }\n");
        sb.append("</style>\n");
        sb.append("</head>\n<body>\n");
        sb.append("<div id='graph'></div>\n");
        sb.append("<script>\n");

        // Nodes
        sb.append("var nodes = new vis.DataSet([\n");
        for (int i = 0; i < nodes.size(); i++) {
            FiscalNode node = nodes.get(i);
            sb.append("  { id: ").append(node.id);
            sb.append(", label: '").append(escapeJs(node.label)).append("'");
            sb.append(", title: '").append(escapeJs(node.tooltip)).append("'");

            // Color
            sb.append(", color: { background: '").append(node.color).append("', border: '#666666' }");
            sb.append(", borderWidth: 2");

            // Icon configuration
            sb.append(", shape: 'circularImage', image: '").append(COMPANY_ICON_SVG_DATA).append("'");
            sb.append(", size: 30"); // Slightly smaller for circular image

            // Label styling - Markdown syntax
            sb.append(", font: { multi: 'md', strokeWidth: 0, align: 'center', background: 'white' }");

            sb.append(" }");
            if (i < nodes.size() - 1)
                sb.append(",");
            sb.append("\n");
        }
        sb.append("]);\n");

        // Edges
        sb.append("var edges = new vis.DataSet([\n");
        for (int i = 0; i < edges.size(); i++) {
            FiscalEdge edge = edges.get(i);
            sb.append("  { from: ").append(edge.from);
            sb.append(", to: ").append(edge.to);
            sb.append(", label: '").append(escapeJs(edge.label)).append("'");
            sb.append(", arrows: 'to'");
            sb.append(", title: '").append(escapeJs(edge.tooltip)).append("'");
            sb.append(", color: { color: '#848484', highlight: '#1976D2' }");
            sb.append(", width: 1.5");
            // Background for edge labels for readability
            sb.append(
                    ", font: { align: 'horizontal', multi: true, size: 11, background: 'rgba(255,255,255,0.9)', strokeWidth: 0 }");
            sb.append(" }");
            if (i < edges.size() - 1)
                sb.append(",");
            sb.append("\n");
        }
        sb.append("]);\n");

        // Network options - Force Atlas 2 for NVL-like organic layout
        sb.append("var container = document.getElementById('graph');\n");
        sb.append("var data = { nodes: nodes, edges: edges };\n");
        sb.append("var options = {\n");
        sb.append("  layout: {\n");
        sb.append("    improvedLayout: true\n");
        sb.append("  },\n");
        sb.append("  physics: {\n");
        sb.append("    enabled: true,\n");
        sb.append("    solver: 'forceAtlas2Based',\n");
        sb.append("    forceAtlas2Based: {\n");
        sb.append("      gravitationalConstant: -200,\n");
        sb.append("      centralGravity: 0.005,\n");
        sb.append("      springLength: 250,\n");
        sb.append("      springConstant: 0.05,\n");
        sb.append("      damping: 0.4\n");
        sb.append("    },\n");
        sb.append("    stabilization: { iterations: 200 }\n");
        sb.append("  },\n");
        sb.append("  nodes: {\n");
        sb.append("    borderWidth: 0,\n");
        sb.append("    shadow: true\n");
        sb.append("  },\n");
        sb.append("  edges: {\n");
        sb.append("    shadow: false,\n");
        sb.append("    smooth: { type: 'curvedCW', roundness: 0.2 }\n");
        sb.append("  },\n");
        sb.append("  interaction: {\n");
        sb.append("    navigationButtons: true,\n");
        sb.append("    keyboard: true,\n");
        sb.append("    tooltipDelay: 200\n");
        sb.append("  }\n");
        sb.append("};\n");
        sb.append("var network = new vis.Network(container, data, options);\n");
        sb.append("network.on('click', function(params) {\n");
        sb.append("  if (params.nodes.length > 0) {\n");
        sb.append("    var nodeId = params.nodes[0];\n");
        sb.append("    var node = nodes.get(nodeId);\n");
        sb.append("    if (window.java) window.java.select(node.title + '\\n' + node.label.replace(/\\*/g, ''));\n");
        sb.append("  } else if (params.edges.length > 0) {\n");
        sb.append("    var edgeId = params.edges[0];\n");
        sb.append("    var edge = edges.get(edgeId);\n");
        sb.append("    if (window.java) window.java.select(edge.title);\n");
        sb.append("  } else {\n");
        sb.append("    if (window.java) window.java.showStats();\n");
        sb.append("  }\n");
        sb.append("});\n");

        sb.append("</script>\n");
        sb.append("</body>\n</html>");

        return sb.toString();
    }

    private String escapeJs(String s) {
        if (s == null)
            return "";
        return s.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "");
    }

    // Data classes
    private static class FiscalNode {
        long id;
        String label;
        String tooltip;
        String color;

        FiscalNode(long id, String label, String tooltip, String color) {
            this.id = id;
            this.label = label;
            this.tooltip = tooltip;
            this.color = color;
        }
    }

    private static class FiscalEdge {
        long from;
        long to;
        String label;
        String tooltip;

        FiscalEdge(long from, long to, String label, String tooltip) {
            this.from = from;
            this.to = to;
            this.label = label;
            this.tooltip = tooltip;
        }
    }

    private class LoadFiscalDataWorker extends SwingWorker<String, Void> {

        @Override
        protected String doInBackground() {
            List<FiscalNode> nodes = new ArrayList<>();
            List<FiscalEdge> edges = new ArrayList<>();
            java.util.Set<Long> nodeIds = new java.util.HashSet<>();

            double gTotalValue = 0;
            double gTotalIcms = 0;
            long gTotalNFe = 0;
            long gTotalCTe = 0;

            try {
                GraphService graphService = GraphServiceFactoryImpl.getInstance().getGraphService();
                GraphDatabaseService graphDb = graphService.getGraphDb();

                if (graphDb == null) {
                    LOGGER.warn("GraphDatabaseService is null");
                    return getEmptyHtml();
                }

                try (Transaction tx = graphDb.beginTx()) {
                    // Try FISCAL_TRANSACTION first, then TRANSACTION
                    // Aggregated query to sum values and count document types
                    String[] queries = {
                            "MATCH (a:ORGANIZATION)-[r:FISCAL_TRANSACTION]->(b:ORGANIZATION) " +
                                    "RETURN a, b, " +
                                    "sum(toFloat(coalesce(r.value, 0))) as totalValue, " +
                                    "sum(toFloat(coalesce(r.icms, 0))) as totalIcms, " +
                                    "sum(CASE WHEN r.doc_type = 'NFe' THEN 1 ELSE 0 END) as countNFe, " +
                                    "sum(CASE WHEN r.doc_type = 'CTe' THEN 1 ELSE 0 END) as countCTe " +
                                    "LIMIT 200"
                    };

                    NumberFormat nf = NumberFormat.getCurrencyInstance(new Locale("pt", "BR"));

                    for (String query : queries) {
                        LOGGER.info("FiscalGraphPanel: Executing query: {}", query);
                        Result result = tx.execute(query);

                        int rowCount = 0;
                        while (result.hasNext()) {
                            rowCount++;
                            java.util.Map<String, Object> row = result.next();
                            Node nodeA = (Node) row.get("a");
                            Node nodeB = (Node) row.get("b");
                            // Relationship is aggregated (no 'r' object)

                            // Add node A
                            if (!nodeIds.contains(nodeA.getId())) {
                                nodes.add(createNode(nodeA));
                                nodeIds.add(nodeA.getId());
                            }

                            // Add node B
                            if (!nodeIds.contains(nodeB.getId())) {
                                nodes.add(createNode(nodeB));
                                nodeIds.add(nodeB.getId());
                            }

                            // Extract aggregated values from Result (Result returns map)
                            double value = parseDoubleSafe(row.get("totalValue"));
                            double icms = parseDoubleSafe(row.get("totalIcms"));
                            long countNFe = ((Number) row.get("countNFe")).longValue();
                            long countCTe = ((Number) row.get("countCTe")).longValue();

                            gTotalValue += value;
                            gTotalIcms += icms;
                            gTotalNFe += countNFe;
                            gTotalCTe += countCTe;

                            StringBuilder edgeLabel = new StringBuilder();
                            edgeLabel.append("Total: ").append(nf.format(value));
                            edgeLabel.append("\nICMS: ").append(nf.format(icms));

                            if (countNFe > 0)
                                edgeLabel.append("\nNFe: ").append(countNFe);
                            if (countCTe > 0)
                                edgeLabel.append("\nCTe: ").append(countCTe);

                            String tooltip = "FISCAL_TRANSACTION" + "\n" + edgeLabel.toString();
                            edges.add(new FiscalEdge(nodeA.getId(), nodeB.getId(), edgeLabel.toString(), tooltip));
                            // ... tooltip assignment ...
                        }

                        LOGGER.info("FiscalGraphPanel: Query returned " + rowCount + " rows.");

                        if (nodes.isEmpty() && rowCount == 0) {
                            LOGGER.warn("FiscalGraphPanel: Aggregated query returned no data. Running diagnostic...");
                            Result diag = tx.execute("MATCH (n)-[r:FISCAL_TRANSACTION]->(m) RETURN count(r) as count");
                            if (diag.hasNext()) {
                                LOGGER.info("Diagnostic: Total FISCAL_TRANSACTION relationships in DB: "
                                        + diag.next().get("count"));
                            } else {
                                LOGGER.info("Diagnostic: No FISCAL_TRANSACTION relationships found.");
                            }
                        }

                        if (!nodes.isEmpty()) {
                            LOGGER.info("FiscalGraphPanel: Found {} nodes and {} edges", nodes.size(), edges.size());
                            break;
                        }
                    }

                    tx.commit();

                    // Format global stats
                    StringBuilder stats = new StringBuilder();
                    stats.append("Total Value: ").append(nf.format(gTotalValue)).append("\n");
                    stats.append("Total ICMS: ").append(nf.format(gTotalIcms)).append("\n");
                    stats.append("Total NFe: ").append(gTotalNFe).append("\n");
                    stats.append("Total CTe: ").append(gTotalCTe);
                    globalStatsText = stats.toString();
                }

            } catch (Exception e) {
                LOGGER.error("Error loading fiscal data", e);
            }

            if (nodes.isEmpty()) {
                return "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>"
                        + "<div style='display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;color:#666;'>"
                        + Messages.getString("FiscalGraphPanel.NoData")
                        + "</div></body></html>";
            }

            return generateGraphHtml(nodes, edges);
        }

        private FiscalNode createNode(Node node) {
            String cnpj = node.hasProperty("cnpj") ? (String) node.getProperty("cnpj") : "?";

            // Correct property keys based on GraphTask.java
            String name = node.hasProperty("name") ? (String) node.getProperty("name")
                    : (node.hasProperty("nome") ? (String) node.getProperty("nome") : cnpj);

            String city = node.hasProperty("city") ? (String) node.getProperty("city")
                    : (node.hasProperty("municipio") ? (String) node.getProperty("municipio") : "");

            String uf = node.hasProperty("state") ? (String) node.getProperty("state")
                    : (node.hasProperty("uf") ? (String) node.getProperty("uf") : "");

            // Split name if it contains semicolons
            if (name.contains(";")) {
                name = name.replace(";", "\n");
            }

            // Markdown formatting for vis.js node labels
            StringBuilder label = new StringBuilder();
            label.append("*").append(name).append("*\n"); // Bold name
            label.append(formatCnpj(cnpj));
            if (!city.isEmpty() || !uf.isEmpty()) {
                label.append("\n").append(city);
                if (!city.isEmpty() && !uf.isEmpty())
                    label.append(" - ");
                label.append(uf);
            }

            String color = STATE_COLORS.getOrDefault(uf, "#E0E0E0");

            return new FiscalNode(node.getId(), label.toString(), "CNPJ: " + cnpj + "\n" + name, color);
        }

        private String formatCnpj(String cnpj) {
            if (cnpj == null || cnpj.length() != 14)
                return cnpj;
            return cnpj.substring(0, 2) + "." + cnpj.substring(2, 5) + "." +
                    cnpj.substring(5, 8) + "/" + cnpj.substring(8, 12) + "-" + cnpj.substring(12);
        }

        @Override
        protected void done() {
            try {
                currentHtml = get();
                Platform.runLater(() -> {
                    webEngine.loadContent(currentHtml);
                    openInBrowserButton.setEnabled(true);
                });
            } catch (Exception e) {
                LOGGER.error("Error displaying fiscal graph", e);
            }
        }
    }

    public class JavaBridge {
        private final JTextArea detailsArea;

        public JavaBridge(JTextArea detailsArea) {
            this.detailsArea = detailsArea;
        }

        public void select(String text) {
            javax.swing.SwingUtilities.invokeLater(() -> {
                if (detailsArea != null) {
                    detailsArea.setText(text);
                    detailsArea.setCaretPosition(0);
                }
            });
        }

        public void showStats() {
            javax.swing.SwingUtilities.invokeLater(() -> {
                if (detailsArea != null) {
                    detailsArea.setText(globalStatsText);
                    detailsArea.setCaretPosition(0);
                }
            });
        }
    }

    private double parseDoubleSafe(Object obj) {
        if (obj == null)
            return 0.0;
        if (obj instanceof Number) {
            return ((Number) obj).doubleValue();
        }
        if (obj instanceof String) {
            try {
                String s = ((String) obj).replace(",", ".");
                return Double.parseDouble(s);
            } catch (NumberFormatException e) {
                return 0.0;
            }
        }
        return 0.0;
    }
}
