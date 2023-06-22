package iped.engine.task;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.commons.io.input.TaggedInputStream;
import org.apache.lucene.queryparser.flexible.standard.QueryParserUtil;
import org.apache.tika.mime.MediaType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import iped.configuration.Configurable;
import iped.data.IItem;
import iped.data.IItemReader;
import iped.engine.config.ConfigurationManager;
import iped.engine.config.EnableTaskProperty;
import iped.engine.core.Manager;
import iped.engine.data.Item;
import iped.engine.datasource.SleuthkitReader;
import iped.engine.search.ItemSearcher;
import iped.engine.task.carver.BaseCarveTask;
import iped.engine.task.index.IndexItem;
import iped.engine.util.TextCache;
import iped.exception.IPEDException;
import iped.parsers.standard.StandardParser;
import iped.properties.BasicProps;
import iped.properties.MediaTypes;
import iped.search.IItemSearcher;
import iped.utils.IOUtil;

public class EmbeddedDiskProcessTask extends AbstractTask {

    private static Logger logger = LoggerFactory.getLogger(EmbeddedDiskProcessTask.class);

    private static final int MIN_DD_SIZE = 1024;

    private static final String ENABLE_PARAM = "processEmbeddedDisks";

    private static final String outputFolder = "embeddedDisks";

    private static Set<MediaType> supportedMimes = MediaType.set(MediaTypes.VMDK, MediaTypes.VMDK_DATA,
            MediaTypes.VMDK_DESCRIPTOR, MediaTypes.VHD, MediaTypes.VHDX, MediaTypes.RAW_IMAGE, MediaTypes.EWF_IMAGE,
            MediaTypes.E01_IMAGE, MediaTypes.EWF2_IMAGE, MediaTypes.EX01_IMAGE);

    private static final String PUSHED_TO_DELETED_QUEUE = "PUSHED_TO_DELETED_DISK_QUEUE";

    private static Set<File> exportedDisks = Collections.synchronizedSet(new HashSet<>());

    private static AtomicBoolean embeddedDiskBeingExpanded = new AtomicBoolean();
    
    private static Object lock = new Object();

    private boolean enabled = true;

    private ArrayList<IItem> deletedDisks = new ArrayList<>();

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public List<Configurable<?>> getConfigurables() {
        return Arrays.asList(new EnableTaskProperty(ENABLE_PARAM));
    }

    @Override
    public void init(ConfigurationManager configurationManager) throws Exception {
        enabled = configurationManager.getEnableTaskProperty(ENABLE_PARAM);

        if (enabled && Manager.getInstance().getNumWorkers() == 1) {
            // abort and warn user because this can cause a deadlock
            throw new IPEDException("To enable '" + ENABLE_PARAM + "' you should have more than 1 Worker thread!");
        }
    }

    @Override
    public void finish() throws Exception {
        if (caseData.containsReport()) {
            exportedDisks.stream().forEach(f -> f.delete());
        }

    }

    public static boolean isSupported(IItem item) {
        return item.getLength() != null && item.getLength() > 0 && !item.isRoot()
                && supportedMimes.contains(item.getMediaType())
                && item.getExtraAttribute(BaseCarveTask.FILE_FRAGMENT) == null;
    }

    public static boolean isFirstOrUniqueImagePart(IItem item) {
        return MediaTypes.E01_IMAGE.equals(item.getMediaType())
                || MediaTypes.EX01_IMAGE.equals(item.getMediaType())
                || MediaTypes.RAW_IMAGE.equals(item.getMediaType())
                || MediaTypes.VMDK_DESCRIPTOR.equals(item.getMediaType());
    }

    @Override
    protected void sendToNextTask(IItem item) throws Exception {
        if (item.getTempAttribute(PUSHED_TO_DELETED_QUEUE) == null) {
            super.sendToNextTask(item);
        }
    }

    @Override
    protected void process(IItem item) throws Exception {
        if (!item.isQueueEnd()) {
            process(item, true);
        } else {
            ArrayList<IItem> deletedList = this.deletedDisks;
            // new list to hold possible deleted disks found in the current deleted ones
            this.deletedDisks = new ArrayList<>();
            for (IItem deletedItem : deletedList) {
                process(deletedItem, false);
                deletedItem.setTempAttribute(PUSHED_TO_DELETED_QUEUE, null);
                sendToNextTask(deletedItem);
            }
        }
    }

    private void process(IItem item, boolean enqueueDeleted) throws Exception {

        if (!isSupported(item)) {
            return;
        }

        if (isFirstOrUniqueImagePart(item)) {
            if (MediaTypes.RAW_IMAGE.equals(item.getMediaType())) {
                // skip some false positives like $MBR files
                if (item.getLength() < MIN_DD_SIZE) {
                    return;
                }
                // look up for DD parts
                ItemSearcher searcher = (ItemSearcher) caseData.getCaseObject(IItemSearcher.class.getName());
                int dotIdx = item.getName().lastIndexOf(".");
                if (dotIdx == -1)
                    dotIdx = item.getName().length();
                String query = BasicProps.PARENTID + ":" + item.getParentId() + " && " + BasicProps.NAME + ":\""
                        + QueryParserUtil.escape(item.getName().substring(0, dotIdx)) + "\"";
                List<IItemReader> possibleParts = searcher.search(query);
                logger.info("Found {} possible image segments of {}", possibleParts.size(), item.getPath());
                for (IItemReader possiblePart : possibleParts) {
                    // export (and process) deleted parts after allocated ones see #1660
                    Collections.sort(possibleParts, new Comparator<IItemReader>() {
                        @Override
                        public int compare(IItemReader o1, IItemReader o2) {
                            return Boolean.compare(o1.isDeleted(), o2.isDeleted());
                        }
                    });
                    exportItem(possiblePart, false);
                }
            }

        } else if (MediaTypes.EWF_IMAGE.equals(item.getMediaType())
                || MediaTypes.EWF2_IMAGE.equals(item.getMediaType())
                || MediaTypes.VMDK_DATA.equals(item.getMediaType())) {

            // process allocated parts & enqueue deleted ones to process later see #1660
            if (item.isDeleted() && enqueueDeleted) {
                deletedDisks.add(item);
                item.setTempAttribute(PUSHED_TO_DELETED_QUEUE, true);
                return;
            } else {
                // export e01/vmdk parts to process them later
                exportItem(item, false);
                return;
            }
        }

        // process allocated parts & enqueue deleted ones to process later see #1660
        if (item.isDeleted() && enqueueDeleted) {
            deletedDisks.add(item);
            item.setTempAttribute(PUSHED_TO_DELETED_QUEUE, true);
            return;
        }

        // export first part if not done
        File imageFile = exportItem(item, true);

        if (embeddedDiskBeingExpanded.getAndSet(true)) {
            super.reEnqueueItem(item);
            return;
        }

        try (SleuthkitReader reader = new SleuthkitReader(true, caseData, output)) {
            logger.info("Decoding embedded disk image {} -> {}", item.getPath(), imageFile.getAbsolutePath());
            reader.read(imageFile, (Item) item);
            int numSubitems = reader.getItemCount();
            if (numSubitems > 0) {
                item.setHasChildren(true);
                item.setExtraAttribute(ParsingTask.HAS_SUBITEM, Boolean.TRUE.toString());
                item.setExtraAttribute(ParsingTask.NUM_SUBITEMS, numSubitems);
            }
            if (reader.hasDecodingError()) {
                item.getMetadata().set(StandardParser.PARSER_EXCEPTION, Boolean.TRUE.toString());
                StandardParser.incParsingErrors();
            } else {
                ((Item) item).setParsedTextCache(new TextCache());
            }
        } finally {
            embeddedDiskBeingExpanded.set(false);
        }
    }

    private File exportItem(IItemReader item, boolean firstPart) throws IOException {
        File imageFile = null;
        if (item instanceof IItem && IOUtil.hasFile((IItem) item)) {
            imageFile = IOUtil.getFile((IItem) item);
        } else {
            String parentTrackId = item.getExtraAttribute(IndexItem.PARENT_TRACK_ID).toString();
            File exportDir = new File(new File(this.output, outputFolder), parentTrackId);
            exportDir.mkdirs();
            imageFile = new File(exportDir, item.getName()).getCanonicalFile();
            boolean alreadyExported = false;

            File trackFile = new File(imageFile.getAbsolutePath() + "_trackID");
            String trackId = item.getExtraAttribute(IndexItem.TRACK_ID).toString();

            synchronized (lock) {
                if (!imageFile.exists()) {
                    Files.writeString(trackFile.toPath(), trackId);
                    imageFile.createNewFile();
                } else {
                    String trackFileId = Files.readString(trackFile.toPath());
                    if (trackId.equals(trackFileId)) {
                        if (imageFile.length() == item.getLength()) {
                            alreadyExported = true;
                        }
                    } else {
                        // exported image refers to a different item with same path, use another output
                        imageFile = new File(exportDir, trackId + "/" + item.getName()).getCanonicalFile();
                        imageFile.getParentFile().mkdirs();
                        if (imageFile.exists() && imageFile.length() == item.getLength()) {
                            alreadyExported = true;
                        }
                    }
                }
            }
            if (!alreadyExported) {
                if (imageFile.length() > 0) {
                    logger.info("Deleting incomplete exported item {} -> {}", item.getPath(), imageFile.getAbsolutePath());
                    imageFile.delete();
                }
                logger.info("Exporting item {} -> {}", item.getPath(), imageFile.getAbsolutePath());
                TaggedInputStream tis = null;
                try (InputStream is = item.getBufferedInputStream()) {
                    tis = new TaggedInputStream(is);
                    Files.copy(tis, imageFile.toPath(), StandardCopyOption.REPLACE_EXISTING);
                } catch (IOException e) {
                    if (tis == null || tis.isCauseOf(e)) {
                        logger.warn("Error reading item {} ({} bytes): {}", item.getPath(), item.getLength(), e.toString());
                    } else {
                        // exception writing data to target file
                        throw e;
                    }
                }
            }
            exportedDisks.add(imageFile);
        }
        return imageFile;
    }

}
