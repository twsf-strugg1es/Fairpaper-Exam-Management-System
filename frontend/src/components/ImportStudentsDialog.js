import React, { useRef, useState } from 'react';
import { LuDownload, LuFileSpreadsheet, LuUpload } from 'react-icons/lu';
import api from '../api';
import { Alert, Button, Checkbox, Modal, UploadProgress, cx } from './ui';
import { errorMessage } from '../utils';
import { useI18n } from '../i18n';

const TEMPLATE = 'email,name\narif.hossain@example.com,Arif Hossain\nnadia.karim@example.com,Nadia Karim\n';

const downloadTemplate = () => {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'students-template.csv';
  link.click();
  URL.revokeObjectURL(url);
};

// Upload a student list -> check it -> enroll the valid rows (organization managers)
export default function ImportStudentsDialog({ open, onClose, onImported, groups }) {
  const { t, tn } = useI18n();
  const [file, setFile] = useState(null);
  const [groupIds, setGroupIds] = useState(new Set());
  const [preview, setPreview] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null); // 'preview' | 'import'
  const [progress, setProgress] = useState(null); // upload, 0..1
  const inputRef = useRef(null);

  const close = () => {
    setFile(null);
    setGroupIds(new Set());
    setPreview(null);
    setReport(null);
    setError('');
    onClose();
  };

  const send = (path, extra) => {
    const body = new FormData();
    body.append('file', file);
    Object.entries(extra || {}).forEach(([k, v]) => body.append(k, v));
    setProgress(0);
    return api.post(path, body, { onUploadProgress: (e) => { if (e.total) setProgress(e.loaded / e.total); } });
  };

  const check = async () => {
    setError('');
    setBusy('preview');
    try {
      setPreview((await send('/org/students/import/preview')).data);
    } catch (err) {
      setError(errorMessage(err, 'Could not read this file'));
    } finally {
      setBusy(null);
      setProgress(null);
    }
  };

  const run = async () => {
    setError('');
    setBusy('import');
    try {
      const { data } = await send('/org/students/import', { group_ids: [...groupIds].join(',') });
      setReport(data);
      onImported();
    } catch (err) {
      setError(errorMessage(err, 'Import failed'));
    } finally {
      setBusy(null);
      setProgress(null);
    }
  };

  const toggleGroup = (id) => {
    const next = new Set(groupIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setGroupIds(next);
  };

  const problems = preview ? preview.rows.filter((r) => r.error) : [];
  const chosenGroups = groups.filter((g) => groupIds.has(g.id)).map((g) => g.name).join(', ');

  const footer = report ? (
    <Button onClick={close}>{t('Done')}</Button>
  ) : (
    <>
      {preview && <Button variant="ghost" onClick={() => setPreview(null)}>{t('Back')}</Button>}
      <Button variant="secondary" onClick={close}>{t('Cancel')}</Button>
      {!preview ? (
        <Button onClick={check} disabled={!file} loading={busy === 'preview'}>{t('Check the list')}</Button>
      ) : (
        <Button onClick={run} icon={LuUpload} disabled={preview.valid === 0} loading={busy === 'import'}>
          {tn(preview.valid, 'Add {{count}} student', 'Add {{count}} students')}
        </Button>
      )}
    </>
  );

  return (
    <Modal
      open={open}
      onClose={close}
      size={preview ? 'lg' : 'md'}
      title={t('Import students')}
      description={report || preview ? null : t('A CSV or Excel file with an "email" column, and optionally a "name" column. Up to 1000 students at a time.')}
      footer={footer}
    >
      {report ? (
        <div className="space-y-3 text-sm">
          <Alert tone="success" title={tn(report.valid, '{{count}} student added', '{{count}} students added')}>
            {chosenGroups ? t('They are in {{groups}}.', { groups: chosenGroups }) : t('They are in no group, so they see exams open to everyone.')}
          </Alert>
          <ul className="space-y-1 text-muted">
            {report.new > 0 && <li>{tn(report.new, '{{count}} new account was invited to set a password (the link works for 7 days).', '{{count}} new accounts were invited to set a password (the link works for 7 days).')}</li>}
            {report.existing > 0 && <li>{tn(report.existing, '{{count}} person already had an account and was told by email.', '{{count}} people already had an account and were told by email.')}</li>}
            {report.members > 0 && <li>{tn(report.members, '{{count}} was already a student here.', '{{count}} were already students here.')}</li>}
            {report.errors > 0 && <li>{tn(report.errors, '{{count}} row was skipped.', '{{count}} rows were skipped.')}</li>}
          </ul>
        </div>
      ) : !preview ? (
        <div className="space-y-5">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={cx(
              'flex w-full flex-col items-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors',
              file ? 'border-brand/50 bg-brand-soft/40' : 'border-line hover:border-muted/50 hover:bg-sunken/50',
            )}
          >
            <LuFileSpreadsheet className={cx('h-8 w-8', file ? 'text-brand' : 'text-muted')} />
            <span className="mt-3 text-sm font-medium">{file ? file.name : t('Choose a .csv or .xlsx file')}</span>
            <span className="mt-1 text-xs text-muted">{file ? t('Click to choose a different file') : t('Saved from Excel, Google Sheets or any spreadsheet')}</span>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => { setFile(e.target.files[0] || null); setError(''); }}
            />
          </button>
          <Button variant="ghost" size="sm" icon={LuDownload} onClick={downloadTemplate}>{t('Download a template')}</Button>
          {groups.length > 0 && (
            <fieldset>
              <legend className="label">{t('Add them to groups')} <span className="ms-1.5 font-normal text-muted">{t('optional')}</span></legend>
              <div className="mt-1 flex flex-wrap gap-x-5 gap-y-2">
                {groups.map((g) => <Checkbox key={g.id} checked={groupIds.has(g.id)} onChange={() => toggleGroup(g.id)}>{g.name}</Checkbox>)}
              </div>
            </fieldset>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm">
            <span className="font-medium">{tn(preview.valid, '{{count}} student ready to add', '{{count}} students ready to add')}</span>
            {preview.errors > 0 && <span className="text-danger"> · {tn(preview.errors, '{{count}} row has a problem and will be skipped', '{{count}} rows have problems and will be skipped')}</span>}
          </p>
          <ul className="flex flex-wrap gap-2 text-xs">
            <li className="tag">{tn(preview.new, '{{count}} new', '{{count}} new')}</li>
            <li className="tag">{tn(preview.existing, '{{count}} with an account', '{{count}} with an account')}</li>
            <li className="tag">{tn(preview.members, '{{count}} already here', '{{count}} already here')}</li>
          </ul>
          {problems.length > 0 && (
            <div className="max-h-72 overflow-y-auto overscroll-contain rounded-lg border border-line">
              <table className="table">
                <thead><tr><th className="w-16">{t('Row')}</th><th>{t('Email')}</th><th>{t('Problem')}</th></tr></thead>
                <tbody>
                  {problems.map((r) => (
                    <tr key={r.row}>
                      <td className="tabular text-muted">{r.row}</td>
                      <td className="break-all">{r.email || '—'}</td>
                      <td className="text-danger">
                        {t(r.error)}
                        {r.first_row && <span className="text-muted"> {t('(first on row {{row}})', { row: r.first_row })}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {chosenGroups && <p className="text-sm text-muted">{t('Everyone added joins {{groups}}.', { groups: chosenGroups })}</p>}
        </div>
      )}
      {busy && progress !== null && <UploadProgress value={progress} className="mt-4" />}
      {error && <Alert tone="danger" className="mt-4">{error}</Alert>}
    </Modal>
  );
}
