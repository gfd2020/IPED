package iped.engine.hashdb;

import iped.utils.HashValue;

public class PhotoDnaItem extends HashValue {
    /**
     * 
     */
    private static final long serialVersionUID = 1L;

    private final int hashId;

    public PhotoDnaItem(int hashId, byte[] hash) {
        super(hash);
        this.hashId = hashId;
    }

    public int getHashId() {
        return hashId;
    }

}
