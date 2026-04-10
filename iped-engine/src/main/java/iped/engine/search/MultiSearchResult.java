package iped.engine.search;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import org.roaringbitmap.RoaringBitmap;

import iped.data.IIPEDSource;
import iped.data.IItemId;
import iped.engine.data.IPEDMultiSource;
import iped.engine.data.IPEDSource;
import iped.engine.data.ItemId;
import iped.search.IMultiSearchResult;

public class MultiSearchResult implements IMultiSearchResult {

    private IItemId[] ids;
    private float[] scores;
    IPEDSearcher ipedSearcher;
    IIPEDSource ipedSource;
    RoaringBitmap docids;
    RoaringBitmap[] casesBitSet = null;

    public MultiSearchResult() {
        this.ids = new ItemId[0];
        this.scores = new float[0];
    }

    public MultiSearchResult(IItemId[] ids, float[] scores) {
        this.ids = ids;
        this.scores = scores;
    }

    public MultiSearchResult(IIPEDSource ipedSource, IItemId[] ids, float[] scores) {
        this.ids = ids;
        this.scores = scores;
    }

    public final int getLength() {
        return ids.length;
    }

    public final IItemId getItem(int i) {
        return ids[i];
    }

    public final float getScore(int i) {
        return scores[i];
    }

    public final void setScore(int i, float score) {
        scores[i] = score;
    }

    public final void setItem(int i, IItemId itemId) {
        ids[i] = itemId;
    }

    public Iterable<IItemId> getIterator() {
        return new ItemIdIterator();
    }

    public class ItemIdIterator implements Iterable<IItemId>, Iterator<IItemId> {

        private int pos = 0;

        @Override
        public final Iterator<IItemId> iterator() {
            return this;
        }

        @Override
        public final boolean hasNext() {
            return pos < ids.length;
        }

        @Override
        public final IItemId next() {
            return ids[pos++];
        }

        @Override
        public void remove() {
            throw new UnsupportedOperationException("Remove not allowed"); //$NON-NLS-1$
        }

        public int getPos() {
            return pos;
        }

        public void setPos(int pos) {
            this.pos = pos;
        }
    }

    public static MultiSearchResult get(IPEDMultiSource iSource, LuceneSearchResult luceneResult) {

        // System.out.println("multi Result");

        ArrayList<IItemId> validIds = new ArrayList<>();
        ArrayList<Float> validScores = new ArrayList<>();
        float[] srcScores = luceneResult.getScores();

        if (luceneResult.getLength() <= IPEDSearcher.MAX_SIZE_TO_SCORE) {
            int[] docs = luceneResult.getLuceneIds();
            for (int i = 0; i < docs.length; i++) {
                IItemId itemId = iSource.getItemId(docs[i]);
                if (itemId != null && itemId.getId() >= 0) {
                    validIds.add(itemId);
                    validScores.add(srcScores[i]);
                }
            }

            // Otimização: considera que itens estão em ordem crescente do LuceneId (qdo não
            // usa scores)
        } else {
            IIPEDSource atomicSource = null;
            int baseDoc = 0;
            int sourceId = 0;
            int maxdoc = 0;
            int[] docs = luceneResult.getLuceneIds();
            for (int i = 0; i < docs.length; i++) {
                if (atomicSource == null || docs[i] >= baseDoc + maxdoc) {
                    atomicSource = iSource.getAtomicSource(docs[i]);
                    sourceId = atomicSource.getSourceId();
                    baseDoc = iSource.getBaseLuceneId(atomicSource);
                    maxdoc = atomicSource.getReader().maxDoc();
                }
                int id = atomicSource.getId(docs[i] - baseDoc);
                if (id >= 0) {
                    validIds.add(new ItemId(sourceId, id));
                    validScores.add(srcScores[i]);
                }
            }
        }

        MultiSearchResult result = new MultiSearchResult();
        result.ids = validIds.toArray(new IItemId[0]);
        result.scores = new float[validScores.size()];
        for (int i = 0; i < result.scores.length; i++) {
            result.scores[i] = validScores.get(i);
        }

        return result;
    }

    public static LuceneSearchResult get(IMultiSearchResult ipedResult, IPEDMultiSource iSource) {
        LuceneSearchResult lResult = new LuceneSearchResult(ipedResult.getLength());
        float[] scores = lResult.getScores();
        int[] docs = lResult.getLuceneIds();

        int i = 0;
        if (ipedResult.getLength() <= IPEDSearcher.MAX_SIZE_TO_SCORE) {
            for (IItemId item : ipedResult.getIterator()) {
                scores[i] = ipedResult.getScore(i);
                docs[i] = iSource.getLuceneId(item);
                i++;
            }

            // Otimização: considera que itens estão em ordem crescente do LuceneId (qdo não
            // usa scores)
        } else {
            IIPEDSource atomicSource = null;
            int baseDoc = 0;
            int sourceId = 0;
            for (IItemId item : ipedResult.getIterator()) {
                if (atomicSource == null || item.getSourceId() != sourceId) {
                    sourceId = item.getSourceId();
                    atomicSource = iSource.getAtomicSourceBySourceId(sourceId);
                    baseDoc = iSource.getBaseLuceneId(atomicSource);
                }
                docs[i] = atomicSource.getLuceneId(item.getId()) + baseDoc;
                scores[i] = ipedResult.getScore(i);
                i++;
            }
        }

        return lResult;
    }

    @Override
    public MultiSearchResult clone() {
        MultiSearchResult result = new MultiSearchResult();
        result.ids = this.ids.clone();
        result.scores = this.scores.clone();
        return result;
    }

    public boolean hasDocId(int docId) {
        return docids.contains(docId);
    }

    public RoaringBitmap getDocIdBitSet() {
        return docids;
    }

    public IPEDSearcher getIpedSearcher() {
        return ipedSearcher;
    }

    public void setIpedSearcher(IPEDSearcher ipedSearcher) {
        this.ipedSearcher = ipedSearcher;
    }

    @Override
    public IIPEDSource getIPEDSource() {
        return ipedSource;
    }

    public void setIPEDSource(IIPEDSource ipedSource) {
        if (this.ipedSource == null || this.docids == null) {
            this.ipedSource = ipedSource;
            this.docids = new RoaringBitmap();
            for (int i = 0; i < ids.length; i++) {
                if (ids[i].getId() < 0) {
                    continue;
                }
                int lucId = ipedSource.getLuceneId(ids[i]);
                if (lucId >= 0) {
                    docids.add(lucId);
                }
            }
        }
    }

    public RoaringBitmap[] getCasesBitSets(IPEDMultiSource multiSource) {
        if (casesBitSet == null) {
            Integer lastSourceId = -1;
            RoaringBitmap bitset = null;
            int maxSrcId = 0;

            List<IPEDSource> cases = multiSource.getAtomicSources();
            for (Iterator iterator = cases.iterator(); iterator.hasNext();) {
                IPEDSource ipedSource = (IPEDSource) iterator.next();
                if (ipedSource.getSourceId() > maxSrcId) {
                    maxSrcId = ipedSource.getSourceId();
                }
            }

            casesBitSet = new RoaringBitmap[maxSrcId + 1];

            for (Iterator iterator = cases.iterator(); iterator.hasNext();) {
                IPEDSource ipedSource = (IPEDSource) iterator.next();
                casesBitSet[ipedSource.getSourceId()] = new RoaringBitmap();
            }

            for (int i = 0; i < ids.length; i++) {
                int sourceId = ids[i].getSourceId();
                if (sourceId != lastSourceId) {
                    bitset = casesBitSet[ids[i].getSourceId()];
                    lastSourceId = sourceId;
                }
                bitset.add(ids[i].getId());
            }

        }
        return clone(casesBitSet);
    }

    private RoaringBitmap[] clone(RoaringBitmap[] casesBitSet2) {
        RoaringBitmap[] lcasesBitSet = new RoaringBitmap[casesBitSet.length];
        for (int i = 0; i < casesBitSet.length; i++) {
            lcasesBitSet[i] = new RoaringBitmap();
            lcasesBitSet[i].or(casesBitSet[i]);
        }
        return lcasesBitSet;
    }

}
