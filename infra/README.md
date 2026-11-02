# Infraestructura: plataforma de alquileres Montevideo

Cuatro templates de CloudFormation repartidos en los tres repos. Cada repo
despliega solo lo suyo desde su CI, y se conectan entre sí con **exports** de
CloudFormation (`Fn::ImportValue`) que siguen la convención
`${Project}-${Environment}-<Nombre>`.

```
cuadra-backend/infra/base.yaml       → stack alquileres-prd-base      (workflow manual "Deploy base")
cuadra-backend/infra/backend.yaml    → stack alquileres-prd-backend   (CI del backend)
cuadra-frontend/infra/frontend.yaml  → stack alquileres-prd-frontend  (CI del frontend)
cuadra-data/infra/pipeline.yaml      → stack alquileres-prd-pipeline  (CI de la data layer)
```

## Por qué un stack base aparte

La red, los security groups, los endpoints, el topic de alertas, el bucket de
artefactos y los roles de OIDC para GitHub los usan los tres repos. Si vivieran en el
stack de uno de ellos, ese repo podría romper a los otros dos en un deploy cualquiera.
El stack base cambia muy poco, lo despliega alguien con permisos de admin y
vive en el repo del backend (también podría ir en un repo propio de infraestructura).

Los security groups van todos en `base.yaml` porque se referencian entre sí.

## Qué exporta cada stack

| Stack | Exporta | Lo usan |
| --- | --- | --- |
| base | VPC, subnets, AZs de las subnets app, security groups, topic de alertas, bucket de artefactos | backend, pipeline |
| backend | DNS del ALB, endpoint y secreto de la DB, Cognito, nombre del secreto del header de origen | frontend (secreto por nombre), pipeline |
| frontend | nada | |
| pipeline | nada | |

Un export que otro stack importa no se puede cambiar ni borrar hasta quitar el
import. Conviene no renombrar outputs de `base` ni `backend`.

## Qué hay que configurar en cada repo

Todos los workflows se autentican con `aws-actions/configure-aws-credentials`
usando OIDC (sin claves) y despliegan con
`--role-arn ${{ secrets.CFN_EXEC_ROLE_ARN }}`.

**Secrets** (Settings → Secrets and variables → Actions → Secrets)

| Secret | Repos | De dónde sale |
| --- | --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | los tres | outputs del stack base: `FrontendDeployRoleArn` / `BackendDeployRoleArn` / `PipelineDeployRoleArn` |
| `CFN_EXEC_ROLE_ARN` | los tres | output `CfnExecutionRoleArn` del stack base |
| `AWS_BASE_DEPLOY_ROLE_ARN` | backend | rol de OIDC con permisos de admin, para el workflow "Deploy base" (ver abajo) |
| `GOOGLE_CLIENT_ID` | backend | Client ID del cliente OAuth de Google Cloud, para el login con Google. Vacío = el user pool queda sin el proveedor Google |
| `GOOGLE_CLIENT_SECRET` | backend | Client secret del mismo cliente OAuth |
| `VITE_CARTO_API_KEY` | frontend | key de [CARTO basemaps](https://carto.com/basemaps) para los tiles del mapa. Sin ella CARTO responde 200 pero manda una imagen que dice "API KEY REQUIRED" y el mapa se ve roto. Es una key de frontend (queda visible en el bundle): restringila por dominio en el panel de CARTO |

**Variables** (misma pantalla → Variables)

| Variable | Repos | Default | Para qué |
| --- | --- | --- | --- |
| `AWS_REGION` | los tres | `us-east-1` | región de todos los stacks |
| `PROJECT` | los tres | `alquileres` | prefijo de stacks y exports |
| `ENVIRONMENT` | los tres | `prd` | `dev` o `prd` |
| `ORIGIN_CERTIFICATE_ARN` | backend | — (opcional) | certificado ACM de `origin.<dominio>` para el ALB. **Vacío = el ALB escucha en 80 sin TLS**, ver "Sin dominio todavía" |
| `INSTANCE_TYPE` | backend | `t3.micro` | opcional |
| `SITE_DOMAIN_NAME` | frontend | — | dominio público, por ejemplo `www.<dominio>` |
| `AUTH_CALLBACK_URLS` | backend | `http://localhost:5173/` | URLs a las que Cognito vuelve después del login, separadas por coma. **La raíz del sitio, no un path** (ver abajo) |
| `AUTH_LOGOUT_URLS` | backend | `http://localhost:5173/` | ídem para el logout |
| `AUTH_DOMAIN_PREFIX` | backend | `<Project>-<Environment>-auth` | prefijo del dominio de Cognito. Es único en toda la región, no solo en la cuenta |
| `ENABLE_COGNITO_AUTH` | backend | `false` | `true` = la API solo acepta ID tokens de Cognito y apaga el login con contraseña |
| `ORIGIN_DOMAIN_NAME` | frontend | — | `origin.<dominio>` (el CNAME al ALB) |
| `SITE_CERTIFICATE_ARN` | frontend | — | certificado ACM de `SITE_DOMAIN_NAME`, en us-east-1 |
| `SCHEDULE_EXPRESSION` | data | `cron(0 6 ? * MON *)` | opcional, cuándo corre el pipeline |
| `GH_ORG`, `FRONTEND_REPO`, `BACKEND_REPO`, `PIPELINE_REPO`, `ALERT_EMAIL` | backend | — | solo para el workflow "Deploy base" |
| `GH_ORG_ID`, `FRONTEND_REPO_ID`, `BACKEND_REPO_ID`, `PIPELINE_REPO_ID` | backend | — | ids numéricos de GitHub, para el claim `sub` inmutable del token OIDC. Solo para "Deploy base". Sacarlos con `gh api /users/<org> --jq .id` y `gh api /repos/<org>/<repo> --jq .id` |

(`GH_ORG` y no `GITHUB_ORG`: GitHub reserva el prefijo `GITHUB_`.)

### El claim `sub` inmutable de GitHub

En los repos creados desde 2025, GitHub manda el claim `sub` del token OIDC como
`repo:<org>@<orgId>/<repo>@<repoId>:ref:refs/heads/main`, no como
`repo:<org>/<repo>:ref:refs/heads/main`. Una trust policy escrita solo para la forma
clásica falla con **`Not authorized to perform sts:AssumeRoleWithWebIdentity`**, que
parece un problema de permisos y en realidad es una comparación de strings que no da.

Los tres roles de deploy de `base.yaml` aceptan las dos formas (`StringLike` con los
dos strings), así que sirven antes y después de que GitHub migre un repo, y sobreviven
a un rename. Por eso hacen falta las variables `*_REPO_ID` y `GH_ORG_ID`.

Para ver en qué forma está un repo:
`gh api /repos/<org>/<repo>/actions/oidc/customization/sub`
(un 404 significa que el repo es anterior a la función y usa la forma clásica).

## Cuenta con plan FREE

Chequear con `aws freetier get-account-plan-state`. Si devuelve
`accountPlanType: FREE`, la cuenta tiene límites de plan (no solo de uso) y el
stack del backend **no se crea con los defaults**: la RDS falla con
`The specified backup retention period exceeds the maximum available to free
tier customers` y el stack queda en `ROLLBACK_FAILED`.

Variables a cargar en el repo del backend para ese caso:

| Variable | Valor | Por qué |
| --- | --- | --- |
| `DB_MULTI_AZ` | `false` | Multi-AZ no entra en el plan FREE |
| `DB_BACKUP_RETENTION_DAYS` | `1` | 7 excede el máximo del plan |
| `DB_DELETION_PROTECTION` | `false` | Deja bajar el stack sin pasos manuales |

Los defaults del template siguen siendo los de producción de verdad
(Multi-AZ, 7 días de backup, protección activa): estas variables los bajan a
propósito y solo en el repo donde se cargan.

**La base queda en una sola zona y con un día de backup.** Sirve para probar;
no es una base de producción. Antes de tratarla como tal hay que sacar estas
variables y volver a desplegar.

El plan FREE también bloquea otras cosas: `route53domains` no está disponible,
por ejemplo. Y trae crédito limitado -- `accountPlanRemainingCredits` dice
cuánto queda y `accountPlanExpirationDate` hasta cuándo.

### Si un create falla y el rollback queda trabado

Con `DB_DELETION_PROTECTION=true`, un create fallido deja el stack en
`ROLLBACK_FAILED`: CloudFormation no puede borrar el user pool de Cognito ni la
RDS. Para destrabarlo:

```bash
aws cognito-idp update-user-pool --user-pool-id <id> --deletion-protection INACTIVE
aws cloudformation delete-stack --stack-name alquileres-<env>-backend
```

Con la variable en `false` esto no pasa, porque los dos recursos se crean sin
protección.

## Sin dominio todavía

Se puede desplegar `base` y `backend` y probar todo el pipeline de CI/CD **antes** de
comprar el dominio, aceptando que el tráfico al ALB va sin TLS:

- Dejar `ORIGIN_CERTIFICATE_ARN` sin cargar. `backend.yaml` crea un listener HTTP en
  el puerto 80 en vez del HTTPS en 443 (parámetro `OriginCertificateArn` vacío).
- Desplegar `base` con `AllowAlbHttp=true` (input `allow_alb_http` del workflow
  "Deploy base"), que abre el 80 del `AlbSG`. Sigue restringido a la prefix list de
  CloudFront, igual que el 443.
- El default del listener es `403` en los dos modos: solo pasa el tráfico que trae el
  header secreto `X-Origin-Verify` que agrega CloudFront.

Al cargar el certificado: poner `ORIGIN_CERTIFICATE_ARN`, volver a desplegar `base`
con `AllowAlbHttp=false` y el backend. El listener vuelve a 443 solo y el 80 se cierra.

**El `frontend` tampoco necesita dominio.** Sin `SITE_DOMAIN_NAME`/`SITE_CERTIFICATE_ARN`,
CloudFront sirve el sitio en su propio nombre (`dxxxx.cloudfront.net`) con el
certificado que AWS mantiene y renueva, y el origen de `/api/*` pasa a ser el DNS del
ALB directo (export `<proyecto>-<env>-AlbDnsName`) en vez de un CNAME `origin.<dominio>`.
`VITE_API_BASE_URL` es relativa (`/api`), así que funciona igual en los dos modos.

En ese modo el salto CloudFront -> ALB va **sin cifrar**, y con él el header secreto
`X-Origin-Verify`. El security group del ALB solo acepta la prefix list de CloudFront,
así que nadie más llega, pero el tramo viaja en claro: para producción de verdad hay
que cargar los certificados.

## Orden del primer despliegue

1. **Certificados ACM** (a mano, en us-east-1): `www.<dominio>` para CloudFront y
   `origin.<dominio>` para el ALB. Validarlos cargando los CNAME en el proveedor DNS.
2. **base**. Dos formas:
   - El workflow **Deploy base** de este repo (`workflow_dispatch`), que necesita
     el secret `AWS_BASE_DEPLOY_ROLE_ARN`. Problema del huevo y la gallina: ese
     rol lo crea el propio `base.yaml`, así que la primera vez va a mano:
   - A mano, con un usuario admin:
     ```bash
     aws cloudformation deploy --stack-name alquileres-prd-base \
       --template-file infra/base.yaml \
       --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
       --parameter-overrides GitHubOrg=<org> FrontendRepo=<repo> BackendRepo=<repo> \
         PipelineRepo=<repo> AlertEmail=<mail>
     ```
   Confirmar la suscripción de SNS que llega por mail. Copiar los ARN de los tres roles
   de deploy (outputs) a los secrets de cada repo como `AWS_DEPLOY_ROLE_ARN`, y el de
   `CfnExecutionRoleArn` como `CFN_EXEC_ROLE_ARN`.
3. **backend**, desde su CI (el workflow construye la AMI con Packer antes del deploy).
4. Cargar en el proveedor DNS el CNAME `origin.<dominio>` → output `AlbDnsName`.
5. ~~**Migración inicial**: crear el usuario `app_user`.~~ Ya no hace falta: lo crea
   el custom resource `DbBootstrap` del stack del backend, en cada create/update
   (`lambdas/db_bootstrap/app.py`). Es el único componente que lee el secreto del
   administrador de la RDS, corre dentro de la VPC porque la base está en subredes
   privadas, y es idempotente -- si el rol ya existe le sincroniza la contraseña con
   el secreto. El Auto Scaling Group depende de él: la app corre `init_db()` al
   importar, así que sin el rol las instancias no pasan el health check. La rotación
   multi-usuario crea después el clon `app_user_clone` sola.
6. **frontend**, desde su CI. Cargar el CNAME `www.<dominio>` → output
   `DistributionDomainName`.
7. **pipeline**, desde el CI de `cuadra-data`.

Este orden no es una sugerencia: hay dependencias duras entre stacks.
`infra/pipeline.yaml` importa `alquileres-<env>-AppDbSecretArn`, que exporta el stack
del backend, así que **`pipeline` no puede crearse antes que `backend`**. Si se lanza
antes, muere al instante con `No export named alquileres-<env>-AppDbSecretArn found` y
queda en `ROLLBACK_COMPLETE`: hay que borrar esa carcasa con `delete-stack` antes de
reintentar. El `frontend` lee del backend los outputs de Cognito en tiempo de build.

Ojo: el paso "Chequear configuración del repo" de cada workflow mira solo **sus
propios** secrets y variables. Un repo puede pasar ese chequeo y fallar igual por un
export que todavía no existe.

Después del primer despliegue completo, cada repo despliega por su cuenta.

## Qué hace cada CI

**Backend** (`.github/workflows/deploy.yml`)
1. Tests (`uv run pytest`).
2. `uv export` del requirements y empaquetado de `app/` en `app.tgz`.
3. Subida a `s3://<artefactos>/backend/<sha>/app.tgz`.
4. Packer genera la AMI (`packer/api.pkr.hcl`: instancia temporal en `PublicSubnetA`
   con IP pública y el instance profile `PackerInstanceProfileName`; la AMI deja el
   venv y la unidad systemd `alquileres-api`).
5. Opcional (`workflow_dispatch` con `snapshot_db`): `aws rds create-db-snapshot`
   antes de desplegar, para cuando el deploy trae migraciones.
6. `aws cloudformation deploy` de `backend.yaml` con `AmiId=<ami nueva>`
   (capabilities `CAPABILITY_IAM CAPABILITY_AUTO_EXPAND`, por el transform de Secrets Manager).
7. `aws autoscaling start-instance-refresh --preferences MinHealthyPercentage=50`,
   y espera a que termine.

**Frontend** (`cuadra-frontend/.github/workflows/deploy.yml`)
1. Lint.
2. Lee `UserPoolId` y `UserPoolClientId` de los outputs del stack backend y los
   pasa al build como variables de entorno, junto con `VITE_API_BASE_URL`.
3. `npm run build`.
4. `aws cloudformation deploy` de `frontend.yaml`.
5. `aws s3 sync dist/ s3://<site bucket> --delete` y
   `aws cloudfront create-invalidation --paths /index.html`.

**Data layer** (`cuadra-data/.github/workflows/deploy.yml`)
1. Tests de los extractores y del pipeline con datos de ejemplo.
2. Zip de la Lambda de scraping (extractor + handler + dependencias),
   `glue/transform.py` y `deps.zip` (pg8000) a `s3://<artefactos>/pipeline/<sha>/`,
   después de importar el handler desde el zip para que una dependencia que
   falte no aparezca recién en la primera corrida.
3. `aws cloudformation deploy` de `pipeline.yaml` con `CodeVersion=<sha>`.
4. Opcional (`workflow_dispatch` con `correr_validacion`):
   `aws stepfunctions start-execution` para validar el cambio sin esperar al cron.

Hoy el pipeline tiene una sola fuente conectada (InfoCasas). El contrato que
tiene que cumplir una fuente nueva está en `cuadra-data/infra/README.md`.

## Notas

- Los prefix list de CloudFront y S3 en `base.yaml` tienen por defecto los IDs de
  us-east-1. Verificarlos antes del primer deploy.
- El SG del ALB usa el prefix list de CloudFront, que cuenta como unas 55 reglas.
  Puede hacer falta pedir un aumento de la cuota de reglas por security group.
- `CfnExecutionRole` tiene `AdministratorAccess` para simplificar. Los roles de deploy
  de cada repo solo pueden operar su propio stack y pasar ese rol. Para producción real
  conviene acotarlo.
- Los roles de OIDC solo confían en `ref:refs/heads/main` de cada repo: los deploys
  desde otra rama no pueden asumirlos (los workflows de CI no lo intentan).
- La tabla `avisos` del catálogo de Glue tiene las columnas del contrato de bronze,
  las mismas que escribe `glue/transform.py`. Si el contrato cambia, se mueven
  juntos (ver `cuadra-data/infra/README.md`).
- El Scheduler no puede darle a la ejecución un nombre por fecha (los nombres no admiten
  `:`). La idempotencia la da la fecha calculada en el primer estado: todas las
  escrituras la usan en sus claves, así que relanzar la misma semana pisa los mismos
  archivos.
- Pendientes conocidos del split, todavía sin resolver: ver
  `PENDIENTES.md` en la raíz de la carpeta `Cuadra/`.


## Login con Cognito y Google

El user pool existía desde el principio pero estaba vacío y desconectado: el
login real era propio (bcrypt en la tabla `users` y un JWT firmado por la
API). El 2026-11-02 se cableó de verdad.

**El corte es de un solo sentido.** En cuanto la API recibe el pool deja de
aceptar su propio JWT, `/auth/register` y `/auth/login` responden 404 y toda
sesión abierta se cae. Por eso va detrás de `ENABLE_COGNITO_AUTH`, que
arranca en `false`: con `false` el dominio y el proveedor de Google se crean
sin tocar el login que está funcionando.

Orden para encenderlo:

1. **Desplegar el backend** sin `GOOGLE_CLIENT_ID`. Crea el dominio del
   hosted UI. El output `GoogleRedirectUri` del stack es la URI que hay que
   pegar en Google.
2. **Crear el cliente OAuth** en Google Cloud (APIs & Services → Credentials
   → OAuth client ID → Web application) y pegar en *Authorized redirect
   URIs* el valor de `GoogleRedirectUri`
   (`https://<dominio>/oauth2/idpresponse`). Guardar el client ID y el secret
   como secrets del repo del backend.
3. **Desplegar el backend otra vez.** Ahora sí crea el proveedor Google
   dentro del pool.
4. **Poner `ENABLE_COGNITO_AUTH=true`** y desplegar backend y frontend. Recién
   acá cambia el login: la API empieza a exigir tokens de Cognito y el
   frontend manda al hosted UI.

**Las URLs de callback entran como variable y no se leen del stack del
frontend**: el dominio de CloudFront lo crea ese stack, que depende de este,
así que referenciarlo sería un ciclo en CloudFormation.

**Tiene que ser la raíz del sitio** (`https://.../`), no `/auth/callback`: la
app rutea por hash y CloudFront no tiene `CustomErrorResponses`, así que
cualquier otro path devolvería un 404 de S3 antes de que cargue nada.
Cognito manda el código como query string y lo levanta `procesarCallback()`
al arrancar la app (ver `cuadra-frontend/src/lib/cognito.js`).

**El nombre de CloudFront cambia cada vez que se recrea el stack del
frontend.** Cuando pase, hay que actualizar `AUTH_CALLBACK_URLS` y
`AUTH_LOGOUT_URLS` y volver a desplegar el backend, o el login corta con
`redirect_mismatch`.
