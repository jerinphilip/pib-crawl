import sys
sys.path.insert(1, '../')
from tqdm import tqdm
from webapp import db
from webapp.models import Entry, Link, Translation, Retrieval
from webapp.retrieval import retrieve_neighbours_en
from sqlalchemy import func, and_


def store_retrieved(model):
    error = open('retrieval_error.txt','w+')
    reqs = db.session.query(Entry.id).all()
    reqs = [req.id for req in reqs]
    queries = db.session.query(Translation)\
                        .filter(and_(Translation.model==model, Translation.parent_id.in_(reqs)))\
                        .all()
    for q in tqdm(queries):
        if q.translated:
            exists = Retrieval.query.filter(and_(Retrieval.query_id==q.parent_id, Retrieval.model==model))\
                              .first()
            if not exists:
                try:
                    retrieved = retrieve_neighbours_en(q.parent_id, model)
                except:
                    print(q.parent_id,file=error)
                    continue
                else:
                    retrieved_id = retrieved[0][0]
                    score = retrieved[0][1]   
                    entry = Retrieval(query_id=q.parent_id, retrieved_id=retrieved_id,\
                                      score=score, model=model)
                    try:
                        db.session.add(entry)
                        db.session.commit()
                    except:
                        print(q.parent_id,file=error)

if __name__ == '__main__':

    parser=ArgumentParser()
    parser.add_argument('model', help='retrieval based on model used for tanslation', required=True)
    args = parser.parse_args()
    model = args.model
    store_retrieved(model)