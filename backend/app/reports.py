from io import BytesIO
from html import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Sequence',fontName='Courier',fontSize=8,leading=12,wordWrap='CJK'))
styles['BodyText'].fontSize=10
styles['BodyText'].leading=15
styles['Title'].textColor=colors.HexColor('#173747')
styles['Heading2'].textColor=colors.HexColor('#137987')
styles['Heading2'].spaceBefore=9
styles['Heading2'].spaceAfter=8
styles['Heading3'].spaceBefore=6
styles['Heading3'].spaceAfter=5
styles.add(ParagraphStyle(name='SmallNote',parent=styles['BodyText'],fontSize=8.5,leading=12,textColor=colors.HexColor('#526575')))
for name in ['Heading1','Heading2','Heading3']:
    styles[name].keepWithNext=True

def para(text, style='BodyText'):
    return Paragraph(escape(str(text)).replace('\n','<br/>'), styles[style])
def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor('#d7e3e6'))
    canvas.line(42,40,A4[0]-42,40)
    canvas.setFont('Helvetica',8)
    canvas.setFillColor(colors.HexColor('#526575'))
    canvas.drawString(42,26,'DeepDTA Research | Interpret with experimental evidence')
    canvas.drawRightString(A4[0]-42,26,f'Page {doc.page}')

def section(story,title,body=None):
    story.extend([Spacer(1,12),para(title,'Heading2')])
    if body: story.append(para(body))

def point(story,title,meaning,action=None):
    group=[para(title,'Heading3'),para(meaning)]
    if action: group.extend([Spacer(1,4),para('What to do: '+action)])
    group.append(Spacer(1,9))
    story.append(KeepTogether(group))

def make_pdf(story,title):
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=48,leftMargin=48,topMargin=48,bottomMargin=58,title=title,author='DeepDTA Research')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()

def warning_action(warning):
    value=warning.lower()
    if 'representation' in value:
        return 'Use a verified canonical SMILES for this exact compound and check whether equivalent SMILES change the score.'
    if 'length exceeds' in value:
        return 'Treat this as extrapolation. Test the model on similarly long inputs or use a model trained for that input range.'
    if 'x residues' in value:
        return 'Confirm ambiguous residues experimentally or from a trusted sequence record before interpreting the score.'
    if 'pair-level' in value or 'unseen' in value:
        return 'Use an independently measured, overlap-checked set of new compounds and targets to test generalisation.'
    return 'Use a matching experimental binding assay and report its conditions and repeatability before relying on the estimate.'

def render_report(predictions, user):
    from .strength_guide import describe
    story=[]
    for index,p in enumerate(predictions):
        if index: story.append(PageBreak())
        story.extend([para('DEEPDTA / RESEARCH','Heading3'),para('Binding affinity report','Title'),
                      para(f'Researcher: {user.name} | Prediction ID: {p.id}','SmallNote'),
                      para(f'Created (UTC): {p.created_at}','SmallNote'),Spacer(1,13)])
        table=Table([[p.dataset.upper(),f'{p.score:.6f}','Predicted pKd' if p.dataset=='davis' else 'KIBA score']],colWidths=[155,165,170])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf3f4')),
                                   ('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#173747')),
                                   ('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),12),
                                   ('TOPPADDING',(0,0),(-1,-1),15),('BOTTOMPADDING',(0,0),(-1,-1),15)]))
        story.append(table)
        guide=describe(p.dataset,p.score)
        section(story,'Predicted binding strength',f"{guide['label']}. {guide['explanation']}")
        story.append(para(guide['basis'],'SmallNote'))
        story.append(para(guide['caution'],'SmallNote'))
        if not p.provenance.get('experimental_evidence'):
            story.extend([Spacer(1,7),para('Published assay records have not been fetched for this result.','SmallNote')])
        if p.dataset=='davis':
            section(story,'What this value means','This is a predicted pKd for the entered drug and protein. Higher predicted pKd means the model expects stronger binding. It is not a laboratory Kd measurement.')
            section(story,'What you can do with it')
            point(story,'Prioritise experiments','Compare candidate compounds scored by the same Davis model for the same protein, then select which to test first.')
            point(story,'Compare with measured Kd','Fetch a matching ChEMBL assay record in the website. When the identity and endpoint checks pass, the PDF can show measured pKd next to the prediction.')
            section(story,'Limits and how to address them')
            point(story,'This number may differ from a real experiment','Davis dataset benchmark metrics describe average error across recorded pairs. Independent external accuracy and calibrated per-result uncertainty remain unestablished.','Measure Kd for the exact compound and protein in a suitable binding assay with replicates. Evaluate the frozen model on an overlap-checked external dataset before claiming general accuracy.')
            point(story,'Binding is not the same as a useful drug','This score does not establish cellular effect, selectivity, safety or clinical benefit.','Follow binding tests with functional, selectivity, ADME and toxicity studies appropriate to the research question.')
        else:
            section(story,'What this value means','This is a predicted KIBA dataset score. It is not Kd, pKd, nM or a percentage chance of binding. Do not convert it to a physical concentration.')
            accuracy=p.provenance.get('numerical_accuracy') or {}
            if accuracy.get('status')=='available':
                section(story,'How accurate might this number be?')
                point(story,f"{accuracy['estimated_accuracy_percent']:.1f}% estimated within +/-{accuracy['tolerance_kiba']:.1f} KIBA units",
                    f"For {accuracy['score_band_calibration_pairs']:,} comparable held-out calibration pairs in this predicted-score range, that percentage had a recorded KIBA value within the stated distance of the model value. On {accuracy['score_band_audit_pairs']:,} separate audit pairs, the observed rate was {accuracy['score_band_audit_percent']:.1f}%.")
                interval=accuracy['prediction_interval']
                point(story,'A range around this prediction',f"The 90% calibrated range is {interval['lower']:.3f} to {interval['upper']:.3f} KIBA units. Across the separate audit pairs, {interval['audit_coverage_percent']:.1f}% of recorded values fell in such a range. This is a group-level check, not a guarantee for this exact compound and protein.")
                story.append(para('These numbers use the supplied KIBA dataset, whose drugs and proteins appeared separately during fitting. They do not validate new compounds, new proteins, or laboratory Kd.','SmallNote'))
            else:
                section(story,'Numerical accuracy estimate unavailable',accuracy.get('reason','No matching calibration data are available for this pair.'))
            section(story,'What you can do with it')
            point(story,'Prioritise pairs','Use scores from the same KIBA model to decide which drug-protein pairs deserve closer review. Keep the scale and model consistent.')
            point(story,'Check recorded examples','Search KIBA reference data to see whether this pair has a recorded dataset value. A reference value is separate from the prediction.')
            section(story,'Limits and how to address them')
            point(story,'Group accuracy may differ for this pair','The deployed model\'s held-out-pair RMSE was 0.4313 KIBA units. The numerical accuracy percentage and range, when available, summarize comparable dataset pairs; a specific prediction can still be wrong by more. Separate cold-split benchmarks use different weights.','Test the frozen deployed model on independent, overlap-checked measured pairs and measure the exact pair in a suitable assay.')
            point(story,'A KIBA score is not measured affinity','It cannot establish Kd or prove binding under a particular assay.','Find a matching experimental record or measure the exact pair directly. Compare only compatible endpoints and units.')
        story.extend([PageBreak(),para('Inputs and model details','Title'),para('This section makes the result traceable. It is not a second prediction.','SmallNote')])
        section(story,'Submitted inputs')
        for title,value in [('Compound',p.drug_name),('Protein',p.protein_name),('Drug SMILES',p.smiles)]:
            story.extend([para(f'{title}: {value}'),Spacer(1,7)])
        section(story,'Protein sequence')
        for start in range(0,len(p.sequence),85): story.append(para(p.sequence[start:start+85],'Sequence'))
        section(story,'Model trace')
        story.extend([para(p.model_version,'Sequence'),Spacer(1,6),para('KIBA was not run.' if p.dataset=='davis' else 'Davis was not run.')])
        if p.dataset=='davis' and p.provenance.get('metrics'):
            section(story,'Davis model evaluation')
            metrics=p.provenance['metrics']['test']
            story.append(para(f"Across {metrics['n']:,} benchmark pairs: MSE {metrics['mse']:.4f}, RMSE {metrics['rmse']:.4f} pKd, concordance index {metrics['concordance_index']:.4f}. Lower MSE and higher concordance are better."))
            story.append(para(p.provenance.get('benchmark_note','')))
            story.append(para('These group statistics are not an accuracy percentage for this particular prediction. Independent experimental comparison remains necessary.','SmallNote'))
        if p.dataset=='kiba':
            section(story,'Architecture and held-out evaluation')
            metrics=p.provenance.get('metrics',{}).get('test',{})
            if metrics: story.append(para(f"Held-out pairs: {metrics.get('n','unknown')}; RMSE: {metrics.get('rmse',0):.4f} KIBA units. These dataset-wide figures do not state this prediction's accuracy."))
            story.append(para('Separate cold-drug and cold-protein benchmark models are not the deployed model.','SmallNote'))
            exposure=p.provenance.get('data_context')
            if exposure:
                section(story,'Training-data context')
                story.append(para(exposure.get('explanation','Training exposure could not be checked.')))
                if exposure.get('status')=='available':
                    story.append(para('Exact compound representation in fitting data: '+('yes' if exposure['drug_seen_in_fit'] else 'no')+'. Exact protein sequence in fitting data: '+('yes' if exposure['protein_seen_in_fit'] else 'no')+'.'))
                    story.append(para('This is an exact-string check, not a chemical similarity test or a confidence score.','SmallNote'))
                test_scope=p.provenance.get('test_exposure')
                if test_scope:
                    story.append(para(f"Of {test_scope['test_pairs']:,} deployed-model test rows, {test_scope['unseen_drug_rows']} had a drug absent from fitting data and {test_scope['unseen_protein_rows']} had a protein absent from fitting data. {test_scope['exact_fit_pair_repeats']} repeated an exact fitting pair; {test_scope['exact_validation_pair_only_repeats']} repeated an exact validation-only pair."))
                    story.append(para('To assess new compounds or targets, evaluate a frozen model on drug-held-out and protein-held-out test sets, then confirm shortlisted pairs experimentally.','SmallNote'))
        if p.dataset=='kiba' and p.provenance.get('data_context'):
            story.append(PageBreak())
        section(story,'Input checks and fixes')
        point(story,'Input identity matters','The score depends on the submitted SMILES and protein sequence. Incorrect stereochemistry, a variant or an unusual representation can change the conclusion.','Verify the compound and full protein sequence. For KIBA, prefer the canonical SMILES representation used in the supplied data.')
        section(story,'Model-specific checks')
        for warning in p.provenance.get('warnings',[]):
            point(story,'Caution',warning,warning_action(warning))
        if p.dataset=='davis':
            story.append(para('No calibrated confidence interval is available.','SmallNote'))
        for source in p.provenance.get('sources',[]): story.append(para(source,'SmallNote'))
        append_experimental_evidence(story,p)
    return make_pdf(story,'DeepDTA Research - Binding affinity report')


def source_link(label, url):
    # Only supported scientific source URLs are linked; all text is escaped.
    from urllib.parse import urlparse
    parsed=urlparse(str(url))
    if parsed.scheme=='https' and parsed.hostname in {'www.ebi.ac.uk','www.rcsb.org','data.rcsb.org','go.drugbank.com'}:
        return Paragraph(f'<a href="{escape(str(url),quote=True)}" color="#166784">{escape(label)}</a>',styles['BodyText'])
    return para(label)

def append_experimental_evidence(story, prediction):
    evidence=prediction.provenance.get('experimental_evidence')
    if evidence is None:
        return
    story.extend([PageBreak(),para('Experimental evidence comparison','Title'),
        para(f'Prediction ID: {prediction.id}'),
        para(f"Compound: {evidence.get('compound_id','Not specified')} | Target: {evidence.get('accession','Not specified')}"),
        para(f"Retrieved (UTC): {evidence.get('retrieved_at','Not recorded')}"),
        para(f"Website prediction: {prediction.score:.6f} {'pKd' if prediction.dataset=='davis' else 'KIBA score'}"),
        para('These are selected published assay records, separate from the model score. They are not an independent accuracy test.'),
        para('Saved evidence snapshot. Downloading this PDF does not perform a new database lookup.','SmallNote'),
        para('Reference sequence matches.' if evidence.get('sequence_match') else 'Reference sequence does not match; numerical comparison is disabled.'),
        para(f"Records included: {evidence.get('returned',len(evidence.get('records',[])))} of {evidence.get('total_matching','unknown')}.")])
    if evidence.get('truncated'): story.append(para('Only the first 50 matching records were retrieved; this report is not exhaustive.'))
    records=evidence.get('records',[])
    if not records: story.append(para(evidence.get('message') or 'No matching experimental records found. This does not mean there is no binding.'))
    for number,r in enumerate(records,1):
        story.extend([para(f"{number}. {r.get('endpoint') or 'Unspecified endpoint'} {r.get('relation') or '(relation unspecified)'} {r.get('value') if r.get('value') is not None else 'not reported'} {r.get('units') or ''}",'Heading2'),
            para(r.get('description') or 'No assay description supplied.'),
            para(f"Activity: {r.get('activity_id')} | Assay: {r.get('assay_id')} | Year: {r.get('year') or 'Not specified'}"),
            para(f"Assigned organism: {r.get('organism') or 'Not specified'}"),
            para(f"Target assignment: {r.get('confidence_description') or 'Not specified'} (ChEMBL score {r.get('confidence','unknown')})")])
        if r.get('numerically_comparable'):
            story.extend([para(f"Experimental pKd: {r['experimental_pkd']:.6f}"),
                para(f"Prediction minus experimental pKd: {r['prediction_minus_experimental_pkd']:.6f}"),
                para(f"Absolute difference: {r['absolute_error_pkd']:.6f} pKd"),
                para('Endpoint and reference identity checks passed. Exact experimental construct, conditions and training-data overlap remain unverified.')])
        else:
            story.append(para('No numerical comparison','Heading3'))
            for reason in r.get('reasons',[]): story.append(para('- '+reason))
        for label,key in [('Activity record','source_url'),('Assay details','assay_url'),('Publication record','document_url')]:
            if r.get(key):
                story.append(source_link(label,r[key]))
                story.append(para(r[key],'Sequence'))
    section(story,'How to strengthen this comparison',
        'Confirm the exact compound structure and protein construct, endpoint, units and assay conditions. Repeat a suitable binding experiment for decisions that depend on the value. To assess model accuracy, test a preselected set of measured pairs and check that none were used for training.')
    story.append(para('No ChEMBL record does not mean the pair cannot bind. A selected literature comparison is not independent model validation.','SmallNote'))
