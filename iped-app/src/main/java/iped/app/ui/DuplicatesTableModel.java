/*
 * Copyright 2012-2014, Luis Filipe da Cruz Nassif
 * 
 * This file is part of Indexador e Processador de Evidências Digitais (IPED).
 *
 * IPED is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * IPED is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with IPED.  If not, see <http://www.gnu.org/licenses/>.
 */
package iped.app.ui;

import java.awt.Rectangle;

import javax.swing.ListSelectionModel;

import org.apache.commons.lang3.StringUtils;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.IntPoint;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.BooleanClause;
import org.apache.lucene.search.BooleanClause.Occur;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.Query;
import org.apache.lucene.search.TermQuery;

import iped.engine.task.index.IndexItem;
import iped.properties.BasicProps;

public class DuplicatesTableModel extends BaseTableModel {

    private static final long serialVersionUID = 1L;

    public DuplicatesTableModel() {
        sortResultsBy = BasicProps.PATH;
    }

    @Override
    public Object getValueAt(int row, int col) {
        if (col == 3) {
            try {
                Document doc = App.get().appCase.getSearcher().doc(results.getLuceneIds()[row]);
                return doc.get(IndexItem.PATH);
            } catch (Exception e) {
            }
            return "";
        }
        return super.getValueAt(row, col);
    }

    @Override
    public void valueChanged(ListSelectionModel lsm) {
        App.get().getTextViewer().textTable.scrollRectToVisible(new Rectangle());

        FileProcessor parsingTask = new FileProcessor(results.getLuceneIds()[selectedIndex], false);
        parsingTask.execute();

        App.get().parentItemModel.fireTableDataChanged();
    }

    @Override
    public void onListItemsResultsComplete() {
        App.get().duplicateDock.setTitleText(results.getLength() + Messages.getString("DuplicatesTableModel.Duplicates"));
    }

    @Override
    public Query createQuery(Document doc) {
        String hash = doc.get(IndexItem.HASH);
        if (StringUtils.isBlank(hash)) {
            return null;
        }

        String id = doc.get(IndexItem.ID);
        String sourceUUID = doc.get(IndexItem.EVIDENCE_UUID);

        BooleanQuery.Builder queryBuilder = new BooleanQuery.Builder();
        queryBuilder.add(new TermQuery(new Term(IndexItem.HASH, hash.toLowerCase())), Occur.MUST);
        queryBuilder.add(new BooleanClause(new BooleanQuery.Builder()
                .add(IntPoint.newExactQuery(IndexItem.ID, Integer.parseInt(id)), Occur.MUST)
                .add(new TermQuery(new Term(IndexItem.EVIDENCE_UUID, sourceUUID)), Occur.MUST)
                .build(), Occur.MUST_NOT));

        return queryBuilder.build();
    }
}
