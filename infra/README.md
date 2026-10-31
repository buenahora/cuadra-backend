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

**Variables** (misma pantalla → Variables)

| Variable | Repos | Default | Para qué |
| --- | --- | --- | --- |
| `AWS_REGION` | los tres | `us-east-1` | región de todos los stacks |
| `PROJECT` | los tres | `alquileres` | prefijo de stacks y exports |
| `ENVIRONMENT` | los tres | `prd` | `dev` o `prd` |
| `ORIGIN_CERTIFICATE_ARN` | backend | — | certificado ACM de `origin.<dominio>` (para el ALB) |
| `INSTANCE_TYPE` | backend | `t3.micro` | opcional |
| `SITE_DOMAIN_NAME` | frontend | — | dominio público, por ejemplo `www.<dominio>` |
| `ORIGIN_DOMAIN_NAME` | frontend | — | `origin.<dominio>` (el CNAME al ALB) |
| `SITE_CERTIFICATE_ARN` | frontend | — | certificado ACM de `SITE_DOMAIN_NAME`, en us-east-1 |
| `SCHEDULE_EXPRESSION` | data | `cron(0 6 ? * MON *)` | opcional, cuándo corre el pipeline |
| `GH_ORG`, `FRONTEND_REPO`, `BACKEND_REPO`, `PIPELINE_REPO`, `ALERT_EMAIL` | backend | — | solo para el workflow "Deploy base" |

(`GH_ORG` y no `GITHUB_ORG`: GitHub reserva el prefijo `GITHUB_`.)

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
5. **Migración inicial**: crear el usuario `app_user` en Postgres con la contraseña del
   secreto `alquileres/prd/db-app`. La rotación multi-usuario crea después el clon
   `app_user_clone` sola.
6. **frontend**, desde su CI. Cargar el CNAME `www.<dominio>` → output
   `DistributionDomainName`.
7. **pipeline**, desde el CI de `cuadra-data`.

Después de eso, cada repo despliega por su cuenta en el orden que quiera.

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
