package iped.engine.graph;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.regex.*;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;

public class DebugPdfExtraction {

    private static final Pattern cnpjPattern = Pattern
            .compile("\\b(\\d{2}\\s*\\.\\s*\\d{3}\\s*\\.\\s*\\d{3}\\s*/\\s*\\d{4}\\s*-\\s*\\d{2})\\b|\\b(\\d{14})\\b");
    private static Pattern moneyPattern = Pattern.compile("(\\d{1,3}(?:\\.\\d{3})*,\\d{2})");

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println(
                    "Usage: mvn exec:java -Dexec.mainClass=\"iped.engine.graph.DebugPdfExtraction\" -Dexec.args=\"<pdf_path_or_directory>\"");
            return;
        }

        String path = args[0];
        File input = new File(path);

        if (!input.exists()) {
            System.out.println("File/Directory not found: " + path);
            return;
        }

        if (input.isDirectory()) {
            File[] files = input.listFiles((dir, name) -> name.toLowerCase().endsWith(".pdf"));
            if (files != null) {
                for (File f : files) {
                    analyzeFile(f);
                }
            }
        } else {
            analyzeFile(input);
        }
    }

    private static void analyzeFile(File f) {
        System.out.println("---- [file: " + f.getName() + "] -------");
        try (PDDocument doc = PDDocument.load(f)) {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(true);
            String text = stripper.getText(doc);
            processText(text, f.getName());
        } catch (Exception e) {
            System.out.println("Error processing " + f.getName() + ": " + e.getMessage());
        }
        System.out.println("-------");
        System.out.println();
    }

    private static void processText(String text, String filename) {
        String emitCNPJ = null;
        String destCNPJ = null;
        String emitName = null;
        String destName = null;
        String emitCity = null;
        String destCity = null;
        double vProd = 0.0;
        double vICMS = 0.0;

        List<String> textCnpjs = new ArrayList<>();
        Matcher m = cnpjPattern.matcher(text);
        while (m.find()) {
            String val = m.group(0).replaceAll("[^0-9]", "");
            if (isValidCNPJ(val) && !textCnpjs.contains(val))
                textCnpjs.add(val);
        }

        boolean isCTe = (filename.toLowerCase().contains("cte") || text.contains("CONHECIMENTO DE TRANSPORTE")
                || text.contains("DACTE"));

        if (isCTe) {
            // 1. CNPJ Extraction
            emitCNPJ = extractCnpjNearKeyword(text, "REMETENTE", 1500);
            if (emitCNPJ == null)
                emitCNPJ = extractCnpjNearKeyword(text, "EXPEDIDOR", 1500);

            // 2. Name Extraction
            emitName = extractNameAfterKeywordMulti(text, "REMETENTE");
            if (emitName == null)
                emitName = extractNameAfterKeywordMulti(text, "EXPEDIDOR");

            // 3. City Extraction (Merged Line Handling)
            String mergedCityLine = extractMergedCityLine(text);
            if (mergedCityLine != null) {
                emitCity = trimCityCode(extractFormattedCity(mergedCityLine, true));
                destCity = trimCityCode(extractFormattedCity(mergedCityLine, false));
                if (emitCity == null)
                    emitCity = trimCityCode(mergedCityLine);
            } else {
                emitCity = trimCityCode(extractCityState(text, "REMETENTE", 2000));
                if (emitCity == null)
                    emitCity = trimCityCode(extractCityState(text, "EXPEDIDOR", 2000));
                destCity = trimCityCode(extractCityState(text, "DESTINAT\u00C1RIO", 1000));
            }

            destCNPJ = extractCnpjNearKeyword(text, "DESTINAT\u00C1RIO", 800);
            if (destCNPJ == null)
                destCNPJ = extractCnpjNearKeyword(text, "DESTINATARIO", 800);

            // HAF Heuristic
            if (destCNPJ == null && textCnpjs.contains("01992041000174")) {
                destCNPJ = "01992041000174";
            }

            destName = extractNameAfterKeywordMulti(text, "DESTINAT\u00C1RIO");
            if (destName == null)
                destName = extractNameAfterKeywordMulti(text, "DESTINATARIO");

            // Value Logic
            vProd = extractMoneyAfterKeyword(text, "Valor da Carga");
            if (vProd == 0.0)
                vProd = extractMoneyAfterKeyword(text, "Valor Carga");
            if (vProd == 0.0)
                vProd = extractMoneyAfterKeyword(text, "Valor Mercadoria");
            if (vProd == 0.0)
                vProd = extractMoneyAfterKeyword(text, "Valor Total");
            if (vProd == 0.0)
                vProd = extractMoneyAfterKeyword(text, "Valor total do servi\u00E7o");

            // Elimination Strategy for CTe CNPJ
            if (emitCNPJ == null && textCnpjs.size() > 1) {
                String carrierCNPJ = extractCnpjNearKeyword(text, "EMITENTE", 800);
                for (String c : textCnpjs) {
                    if ((destCNPJ == null || !c.equals(destCNPJ)) &&
                            (carrierCNPJ == null || !c.equals(carrierCNPJ))) {
                        emitCNPJ = c;
                        break;
                    }
                }
            }

        } else {
            // NFe Logic
            emitCNPJ = extractCnpjNearKeyword(text, "Emitente", 600);
            if (emitCNPJ == null)
                emitCNPJ = extractCnpjNearKeyword(text, "Remetente", 600);
            destCNPJ = extractCnpjNearKeyword(text, "Destinat\u00E1rio", 600);

            vProd = extractMoneyAfterKeyword(text, "Valor Total");
            if (vProd == 0.0)
                vProd = extractMoneyAfterKeyword(text, "Valor:");
        }

        if (destCNPJ == null && textCnpjs.size() > 1 && emitCNPJ != null) {
            for (String c : textCnpjs) {
                if (!c.equals(emitCNPJ)) {
                    destCNPJ = c;
                    break;
                }
            }
        }

        vICMS = extractMoneyAfterKeyword(text, "Valor do ICMS");
        if (vICMS == 0.0)
            vICMS = extractMoneyAfterKeyword(text, "ICMS:");
        if (vICMS == 0.0)
            vICMS = extractMoneyAfterKeyword(text, "V. ICMS");
        if (vICMS == 0.0)
            vICMS = extractMoneyAfterKeyword(text, "Calculo ICMS");
        if (vICMS == 0.0)
            vICMS = extractMoneyAfterKeyword(text, "ICMS Outra UF");

        String docType = isCTe ? "CTe" : "NFe";

        System.out.println("Extraction Details:");
        System.out.println("  Raw CNPJs found: " + textCnpjs);
        System.out.println("  [EMITTER Node (Remetente)]");
        System.out.println("    CNPJ:    " + (emitCNPJ != null ? emitCNPJ : "WARNING: Not Found"));
        System.out.println("    Name:    " + (emitName != null ? emitName : "WARNING: Not Found"));
        System.out.println("    City:    " + (emitCity != null ? emitCity : "WARNING: Not Found"));
        System.out.println("  [RECEIVER Node (Destinatário)]");
        System.out.println("    CNPJ:    " + (destCNPJ != null ? destCNPJ : "WARNING: Not Found"));
        System.out.println("    Name:    " + (destName != null ? destName : "WARNING: Not Found"));
        System.out.println("    City:    " + (destCity != null ? destCity : "WARNING: Not Found"));
        System.out.println("  [LINK Properties]");
        System.out.println("    doc_type: " + docType);
        System.out.println(String.format("    value:    %.2f", vProd));
        System.out.println(String.format("    icms:     %.2f", vICMS));
    }

    private static String trimCityCode(String city) {
        if (city == null)
            return null;
        // Removes anything after " - " followed by digits (e.g. " - 3304557")
        return city.replaceAll("\\s-\\s\\d+.*$", "").trim();
    }

    private static String extractMergedCityLine(String text) {
        String[] lines = text.split("\n");
        Pattern twoStates = Pattern.compile(".*\\s-\\s[A-Z]{2}\\s.*\\s-\\s[A-Z]{2}\\s.*");
        for (String line : lines) {
            if (twoStates.matcher(line).find() && line.contains("MUNIC\u00CDPIO")) {
                return line.trim();
            }
            if (line.split("\\s-\\s[A-Z]{2}(\\s|$)").length > 2) {
                return line.trim();
            }
        }
        return null;
    }

    private static String extractFormattedCity(String line, boolean first) {
        Pattern p = Pattern.compile("(\\s-\\s[A-Z]{2}\\s-\\s\\d+)");
        Matcher m = p.matcher(line);
        if (m.find()) {
            int endOfFirst = m.end();
            if (first) {
                return line.substring(0, endOfFirst).replaceAll(".*MUNIC\u00CDPIO:", "").trim();
            } else {
                if (endOfFirst < line.length())
                    return line.substring(endOfFirst).trim();
            }
        }
        return null;
    }

    private static String extractNameAfterKeywordMulti(String text, String keyword) {
        String lowerText = text.toLowerCase();
        String lowerKey = keyword.toLowerCase();
        int idx = 0;

        String bestCandidate = null;
        int bestDistance = Integer.MAX_VALUE;

        while ((idx = lowerText.indexOf(lowerKey, idx)) != -1) {
            int start = idx + keyword.length();
            int end = Math.min(text.length(), start + 400);
            String block = text.substring(start, end);

            String[] lines = block.split("\n");
            int currentDist = 0;
            for (String line : lines) {
                String trim = line.trim();

                // SPLIT LOGIC
                if (trim.toLowerCase().contains("destinat\u00E1rio")) {
                    int splitIdx = trim.toLowerCase().indexOf("destinat\u00E1rio");
                    // If we are looking for REMETENTE name, take LEFT side
                    if (keyword.equalsIgnoreCase("REMETENTE")) {
                        trim = trim.substring(0, splitIdx).trim();
                    } else {
                        // If looking for DESTINATARIO, take RIGHT side
                        trim = trim.substring(splitIdx + "destinat\u00E1rio".length()).trim();
                    }
                }

                String rejectionReason = getRejectionReason(trim);
                if (rejectionReason == null) {
                    if (currentDist < 50)
                        return trim;
                    if (currentDist < bestDistance) {
                        bestDistance = currentDist;
                        bestCandidate = trim;
                    }
                    break;
                }
                currentDist += line.length() + 1;
            }
            idx += keyword.length();
        }
        return bestCandidate;
    }

    private static String getRejectionReason(String line) {
        if (line.length() < 3)
            return "Length < 3";
        String lower = line.toLowerCase();

        // Filter out "6352 - Prestacao..."
        if (line.matches("^\\d{4}\\s?-.*"))
            return "Starts with Code";
        if (lower.contains("prestacao de servico"))
            return "Service Desc";

        if (lower.startsWith("cnpj") || lower.startsWith("cpf") || lower.startsWith("insc")
                || lower.startsWith("endere"))
            return "Start with ID/Addr label";

        if (lower.contains("http") || lower.contains("www.") || lower.contains("sefaz"))
            return "URL/Sefaz";
        if (lower.contains("cfop") || lower.contains("natureza") || lower.contains("protocolo"))
            return "Fiscal Header";

        if (lower.startsWith("rua") || lower.startsWith("av ") || lower.contains("bairro")
                || lower.contains("municipio") || lower.contains("munic\u00EDpio"))
            return "Address Start";

        if (lower.contains("galpao") || lower.contains("galp\u00E3o") || lower.contains("distrito")
                || lower.contains("industrial") || lower.contains("entrada"))
            return "Address Keyword";

        if (lower.contains("loja") || lower.contains("sala ") || lower.contains("andar"))
            return "Address Keyword";

        if (lower.contains("@") && (lower.contains(".com") || lower.contains(".br")))
            return "Email";

        if (lower.startsWith("cep:"))
            return "CEP";
        if (lower.startsWith("fone"))
            return "Fone";
        if (lower.startsWith("chave de acesso"))
            return "Chave de Acesso";
        if (lower.startsWith("consulta de autenticidade"))
            return "Portal Header"; // New Filter

        if (lower.equals("remetente") || lower.equals("destinat\u00E1rio"))
            return "Keyword itself";

        if (!line.matches(".*[a-zA-Z].*"))
            return "No Letters";
        if (line.trim().startsWith(":"))
            return "Starts with Colon";

        return null; // Valid
    }

    private static String extractCnpjNearKeyword(String text, String keyword, int windowSize) {
        int idx = text.toLowerCase().indexOf(keyword.toLowerCase());
        if (idx == -1)
            return null;
        int searchEnd = Math.min(text.length(), idx + windowSize);
        String sub = text.substring(idx, searchEnd);
        Matcher m = cnpjPattern.matcher(sub);
        if (m.find()) {
            String val = m.group(0).replaceAll("[^0-9]", "");
            if (isValidCNPJ(val))
                return val;
        }
        return null;
    }

    // ... Money and ValidCNPJ methods remain same
    private static double extractMoneyAfterKeyword(String text, String keyword) {
        int idx = text.toLowerCase().indexOf(keyword.toLowerCase());
        if (idx == -1)
            return 0.0;
        int end = Math.min(text.length(), idx + keyword.length() + 200);
        String sub = text.substring(idx + keyword.length(), end);
        Matcher m = moneyPattern.matcher(sub);
        if (m.find()) {
            return parseDoubleSafe(m.group(1));
        }
        return 0.0;
    }

    private static double parseDoubleSafe(String val) {
        if (val == null || val.isEmpty())
            return 0.0;
        try {
            val = val.replaceAll("[^0-9,.]", "");
            val = val.replace(".", "").replace(",", ".");
            if (val.isEmpty())
                return 0.0;
            return Double.parseDouble(val);
        } catch (NumberFormatException e) {
            return 0.0;
        }
    }

    private static boolean isValidCNPJ(String cnpj) {
        if (cnpj == null || cnpj.length() != 14)
            return false;
        if (cnpj.matches("^(\\d)\\1+$"))
            return false;
        try {
            int sm, i, r, num, peso;
            char dig13 = '0', dig14 = '0';
            sm = 0;
            peso = 2;
            for (i = 11; i >= 0; i--) {
                num = (int) (cnpj.charAt(i) - 48);
                sm = sm + (num * peso);
                peso = peso + 1;
                if (peso == 10)
                    peso = 2;
            }
            r = sm % 11;
            dig13 = (r == 0 || r == 1) ? '0' : (char) ((11 - r) + 48);
            sm = 0;
            peso = 2;
            for (i = 12; i >= 0; i--) {
                num = (int) (cnpj.charAt(i) - 48);
                sm = sm + (num * peso);
                peso = peso + 1;
                if (peso == 10)
                    peso = 2;
            }
            r = sm % 11;
            dig14 = (r == 0 || r == 1) ? '0' : (char) ((11 - r) + 48);
            return (dig13 == cnpj.charAt(12)) && (dig14 == cnpj.charAt(13));
        } catch (Exception e) {
            return false;
        }
    }

    // Placeholder - keep signature
    private static String extractCityState(String text, String keyword, int lookahead) {
        int idx = text.toLowerCase().indexOf(keyword.toLowerCase());
        if (idx == -1)
            return null;
        int searchStart = idx + keyword.length();
        int searchEnd = Math.min(text.length(), searchStart + lookahead);
        String block = text.substring(searchStart, searchEnd);

        String[] lines = block.split("\n");
        for (String line : lines) {
            String logLine = line.trim();
            if (logLine.length() < 3)
                continue;
            String lower = logLine.toLowerCase();

            if (lower.contains("munic\u00EDpio:") || lower.contains("municipio:") || lower.contains("cidade:")) {
                int cIdx = lower.indexOf(":");
                return logLine.substring(cIdx + 1).trim();
            }

            if (logLine.matches(".*\\s-\\s[A-Z]{2}\\s.*") || logLine.matches(".*\\s-\\s[A-Z]{2}$")) {
                return logLine;
            }
        }
        return null;
    }
}
