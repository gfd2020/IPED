package iped.parsers.misc;

import java.io.IOException;
import java.io.InputStream;
import java.io.StringWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.List;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;
import org.apache.tika.metadata.Metadata;

/**
 * Parses PDF text including position information, outputting as JSON.
 * Used for position-aware extractions (e.g. Fiscal Data).
 */
public class PDFPositionalTextParser extends PDFTextStripper {

    // We build a list of JSON objects manually to avoid extra dependencies,
    // or we could use simple string formatting since the structure is flat.
    private List<String> jsonItems;
    private int currentPage;

    public PDFPositionalTextParser() throws IOException {
        super();
        this.jsonItems = new ArrayList<>();
    }

    @Override
    protected void startPage(org.apache.pdfbox.pdmodel.PDPage page) throws IOException {
        super.startPage(page);
        this.currentPage = getCurrentPageNo();
    }

    @Override
    protected void writeString(String text, List<TextPosition> textPositions) throws IOException {
        if (textPositions.isEmpty())
            return;

        TextPosition first = textPositions.get(0);
        TextPosition last = textPositions.get(textPositions.size() - 1);

        float x = first.getXDirAdj();
        float y = first.getYDirAdj();
        float w = last.getXDirAdj() + last.getWidthDirAdj() - x;
        float h = first.getHeightDir(); // Approximation

        // Escape text for JSON
        String cleanText = text.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", " ").replace("\r", " ").replace("\t", " ");

        // Simple JSON object
        String json = String.format(java.util.Locale.US,
                "{\"p\":%d,\"x\":%.2f,\"y\":%.2f,\"w\":%.2f,\"h\":%.2f,\"t\":\"%s\"}",
                currentPage, x, y, w, h, cleanText);

        jsonItems.add(json);
    }

    public String parseToJson(InputStream stream) throws IOException {
        return parseToJson(stream, null);
    }

    public String parseToJson(InputStream stream, Metadata metadata) throws IOException {
        PDDocument doc = null;
        if (stream instanceof org.apache.tika.io.TikaInputStream) {
            java.io.File file = ((org.apache.tika.io.TikaInputStream) stream).getFile();
            if (file != null) {
                doc = PDDocument.load(file);
            }
        }
        if (doc == null) {
            doc = PDDocument.load(stream);
        }

        try (PDDocument d = doc) {
            if (metadata != null) {
                metadata.set("xmpTPg:NPages", String.valueOf(doc.getNumberOfPages()));
            }

            this.setSortByPosition(true);
            this.setStartPage(1);
            this.setEndPage(doc.getNumberOfPages());

            // Dummy writer, we collect in writeString
            Writer dummy = new StringWriter();
            this.writeText(doc, dummy);

            // Build final JSON array
            StringBuilder sb = new StringBuilder();
            sb.append("[");
            for (int i = 0; i < jsonItems.size(); i++) {
                sb.append(jsonItems.get(i));
                if (i < jsonItems.size() - 1) {
                    sb.append(",");
                }
            }
            sb.append("]");
            return sb.toString();
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length < 1) {
            System.err.println("Usage: java iped.parsers.misc.PDFPositionalTextParser <pdf_file>");
            System.exit(1);
        }
        java.io.File file = new java.io.File(args[0]);
        try (InputStream is = new java.io.FileInputStream(file)) {
            PDFPositionalTextParser parser = new PDFPositionalTextParser();
            String json = parser.parseToJson(is);
            System.out.println(json);
        }
    }
}
