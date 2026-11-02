"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useController, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { ApiRequestError } from "@/api/client";
import { createDocument, documentKeys } from "@/api/documents";
import { MAX_PDF_BYTES, PDF_MAGIC } from "@/api/schemas";
import { Row } from "@/components/shell/layout";
import {
  Button,
  Card,
  Dropzone,
  Field,
  FileAlertIcon,
  FileCheckIcon,
  FileIcon,
  Input,
  UploadIcon,
  type DropzoneStatus,
} from "@/components/ui";
import { formatBytes, todayKst } from "@/lib/format";
import { setReviewer, useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";

/*
 * 1.1 의 올리기 폼. 파일을 고르면(끌어 놓기·버튼) 서버와 같은 기준으로 먼저 확인하고,
 * 통과해야 "추출 시작" 버튼이 켜진다. 누르면 그때 올리고 1.2 진행 화면으로 간다.
 * 고르는 순간 올리지 않는 까닭: 올리면 바로 대기열에 들어가 모델 호출 비용이 생긴다.
 */

const MAX_MB = MAX_PDF_BYTES / 1024 / 1024;

const uploadFormSchema = z.object({
  file: z
    .instanceof(File, { message: "PDF 파일을 골라 주세요." })
    .refine((f) => f.name.toLowerCase().endsWith(".pdf"), "PDF 파일만 올릴 수 있습니다. 이름이 .pdf 로 끝나는 파일을 골라 주세요.")
    .refine((f) => f.name.length <= 255, "파일 이름이 너무 깁니다. 255자 이하로 바꿔 주세요.")
    .refine((f) => f.size <= MAX_PDF_BYTES, `파일이 너무 큽니다. ${MAX_MB}MB 이하만 올릴 수 있습니다.`)
    // 이름만 .pdf 인 파일을 서버까지 보내지 않도록 앞 5바이트를 읽어 본다
    .refine(async (f) => (await f.slice(0, PDF_MAGIC.length).text()) === PDF_MAGIC, "PDF 파일이 아닙니다. 내용이 PDF 인 파일을 골라 주세요."),
  /** 비우면 서버가 기준일 없이 처리한다 */
  as_of: z.union([z.iso.date({ message: "기준일은 YYYY-MM-DD 로 적어 주세요." }), z.literal("")]),
  /** 서버로 보내지 않는다. 수정 기록과 결과 PDF에 남길 이름이라 비우고는 시작하지 않는다 */
  reviewer: z
    .string()
    .trim()
    .min(1, "검토자 이름을 적어 주세요.")
    .max(40, "검토자 이름은 40자 이하로 적어 주세요."),
});

type UploadInput = z.input<typeof uploadFormSchema>;
type UploadValues = z.output<typeof uploadFormSchema>;

export function UploadForm() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const {
    control,
    register,
    handleSubmit,
    setError,
    setValue,
    getValues,
    resetField,
    formState: { errors, isValid, isValidating, validatingFields },
  } = useForm<UploadInput, unknown, UploadValues>({
    resolver: zodResolver(uploadFormSchema),
    mode: "onChange",
    defaultValues: { file: undefined, as_of: "", reviewer: "" },
  });
  const { field: fileField } = useController({ control, name: "file" });
  const file = fileField.value instanceof File ? fileField.value : null;

  // 오늘 날짜는 브라우저에서 채운다 (정적 빌드 시점의 날짜가 박히지 않도록)
  useEffect(() => {
    if (!getValues("as_of")) setValue("as_of", todayKst(), { shouldValidate: true });
  }, [getValues, setValue]);

  // 검토자 이름은 브라우저에 저장된 값을 따른다. 머리줄에서 바꿔도 이 칸이 같이 바뀐다.
  const savedReviewer = useReviewer();
  useEffect(() => {
    if (getValues("reviewer") !== savedReviewer) {
      setValue("reviewer", savedReviewer, { shouldValidate: savedReviewer !== "" });
    }
  }, [savedReviewer, getValues, setValue]);
  const reviewerField = register("reviewer", { onChange: (e) => setReviewer(e.target.value) });
  const reviewerValue = useWatch({ control, name: "reviewer" });

  const upload = useMutation({
    mutationFn: ({ file, as_of }: UploadValues) =>
      createDocument(file, { filename: file.name, as_of: as_of || undefined }),
    onSuccess: (doc) => {
      // 다음 화면이 빈 상태로 시작하지 않도록 받은 진행 상태를 미리 넣어 둔다
      queryClient.setQueryData(documentKeys.detail(doc.id), doc);
      void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      router.push(routes.extract(doc.id));
    },
    onError: (err) => {
      if (err instanceof ApiRequestError && (err.status === 400 || err.status === 413)) {
        setError("file", { type: "server", message: err.message });
      } else if (err instanceof ApiRequestError && err.status === 422) {
        setError("root.server", { type: "server", message: `입력값을 서버가 받지 않았습니다: ${err.message}` });
      } else {
        setError("root.server", { type: "server", message: "올리지 못했습니다. 서버가 켜져 있는지 확인하고 다시 눌러 주세요." });
      }
    },
  });

  const busy = upload.isPending;
  const canStart = !!file && isValid && !isValidating && !busy;

  // 상자의 상태: 파일 칸만 본다 (검토자 이름을 치는 동안 상자가 깜빡이지 않도록)
  const fileStatus: DropzoneStatus = errors.file
    ? "invalid"
    : file && validatingFields.file
      ? "checking"
      : file
        ? "ready"
        : "idle";
  const needsReviewer = fileStatus === "ready" && !reviewerValue.trim();

  const onFiles = (files: File[]) => {
    upload.reset();
    if (files.length > 1) {
      // 비우면서 검사를 돌리면 비동기 결과("골라 주세요")가 아래 안내를 덮으므로 검사 없이 처음 값으로 되돌린다
      resetField("file");
      setError("file", { type: "count", message: "한 번에 한 건씩 올립니다. PDF 하나만 골라 주세요." });
      return;
    }
    fileField.onChange(files[0]);
  };

  return (
    <form onSubmit={handleSubmit((values) => upload.mutate(values))} noValidate className="flex flex-col gap-4">
      <Row className="items-stretch">
        <Dropzone
          inputId="file"
          accept="application/pdf,.pdf"
          onFiles={onFiles}
          disabled={busy}
          status={fileStatus}
          describedBy={errors.file ? "file-error" : undefined}
          buttonLabel={file || errors.file ? "다른 파일 선택" : "파일 선택"}
          className="min-h-59 grow-2 basis-115"
        >
          {(over) => <DropzoneContent over={over} status={fileStatus} file={file} error={errors.file?.message} busy={busy} />}
        </Dropzone>

        <Card className="flex grow basis-75 flex-col gap-4.5">
          <h2 className="text-lg font-bold">검증 조건</h2>
          <Field id="as_of" label="기준일" hint="이 날짜의 법령과 기준으로 판정합니다" error={errors.as_of?.message}>
            <Input
              id="as_of"
              type="date"
              disabled={busy}
              aria-invalid={!!errors.as_of}
              aria-describedby={errors.as_of ? "as_of-error" : "as_of-hint"}
              {...register("as_of")}
            />
          </Field>
          <Field
            id="reviewer"
            label="검토자 이름"
            hint="수정 기록과 결과 PDF에 이 이름이 남습니다. 이 브라우저에만 저장됩니다."
            error={errors.reviewer?.message}
          >
            <Input
              id="reviewer"
              autoComplete="name"
              disabled={busy}
              aria-invalid={!!errors.reviewer}
              aria-describedby={errors.reviewer ? "reviewer-error" : "reviewer-hint"}
              {...reviewerField}
            />
          </Field>
        </Card>
      </Row>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-line bg-white px-5 py-3.5">
        {/* 버튼이 왜 꺼져 있는지, 누르면 무엇이 일어나는지를 한 줄로 알린다 */}
        <div className="min-w-0">
          {errors.root?.server ? (
            <p role="alert" className="text-sm text-red">
              {errors.root.server.message}
            </p>
          ) : busy ? (
            <p className="text-mut">파일을 올리고 있습니다. 끝나면 진행 화면으로 넘어갑니다.</p>
          ) : needsReviewer ? (
            <p className="text-amb-text">검토자 이름을 적으면 시작할 수 있습니다.</p>
          ) : fileStatus === "ready" ? (
            <p className="text-grn">준비됐습니다. 추출 시작을 누르면 올리고 진행 화면으로 넘어갑니다.</p>
          ) : fileStatus === "invalid" ? (
            <p className="text-mut">다른 PDF를 골라 주세요.</p>
          ) : fileStatus === "checking" ? (
            <p className="text-mut">고른 파일을 확인하고 있습니다.</p>
          ) : (
            <p className="text-mut">PDF를 고르면 확인한 뒤 시작할 수 있습니다.</p>
          )}
        </div>
        <Button type="submit" variant="primary" size="lg" disabled={!canStart} aria-busy={busy}>
          {busy ? "올리는 중" : "추출 시작"}
        </Button>
      </div>
    </form>
  );
}

/** 상자 안: 상태마다 아이콘·색·문구가 바뀐다 */
function DropzoneContent({
  over,
  status,
  file,
  error,
  busy,
}: {
  over: boolean;
  status: DropzoneStatus;
  file: File | null;
  error?: string;
  busy: boolean;
}) {
  if (over) {
    return (
      <>
        <UploadIcon className="text-blue" />
        <p className="text-lg font-medium text-blue2">여기에 놓으세요</p>
        <p className="text-mut">PDF 하나를 놓으면 바로 확인합니다</p>
      </>
    );
  }
  if (status === "invalid") {
    return (
      <>
        <FileAlertIcon className="text-red" />
        <p className="max-w-full truncate text-lg font-medium">{file?.name ?? "올릴 수 없습니다"}</p>
        <p id="file-error" role="alert" className="text-red">
          {error}
        </p>
      </>
    );
  }
  if (status === "checking" && file) {
    return (
      <>
        <FileIcon className="text-blue" />
        <p className="max-w-full truncate text-lg font-medium">{file.name}</p>
        <p className="text-mut">PDF인지 확인하는 중입니다</p>
      </>
    );
  }
  if (status === "ready" && file) {
    return (
      <>
        <FileCheckIcon className="text-grn" />
        <p className="max-w-full truncate text-lg font-medium">{file.name}</p>
        <p className="font-medium text-grn">
          {formatBytes(file.size)} · {busy ? "올리는 중입니다" : "올릴 수 있습니다"}
        </p>
      </>
    );
  }
  return (
    <>
      <UploadIcon className="text-outline" />
      <p className="text-lg font-medium">검수할 PDF를 이 영역으로 끌어 놓으세요</p>
      <p className="text-mut">한 번에 한 건씩, {MAX_MB}MB까지 올립니다</p>
    </>
  );
}
