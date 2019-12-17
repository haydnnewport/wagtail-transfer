import os.path
import shutil
from unittest import mock

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.images import ImageFile
from django.test import TestCase
from wagtail.core.models import Collection, Page
from wagtail.images.models import Image

from wagtail_transfer.models import IDMapping
from wagtail_transfer.operations import ImportPlanner
from tests.models import (
    Advert, Author, ModelWithManyToMany, PageWithParentalManyToMany, PageWithRelatedPages,
    PageWithRichText, PageWithStreamField, RedirectPage, SectionedPage, SimplePage, SponsoredPage
)

# We could use settings.MEDIA_ROOT here, but this way we avoid clobbering a real media folder if we
# ever run these tests with non-test settings for any reason
TEST_MEDIA_DIR = os.path.join(os.path.join(settings.BASE_DIR, 'test-media'))
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fixtures')


class TestImport(TestCase):
    fixtures = ['test.json']

    def setUp(self):
        shutil.rmtree(TEST_MEDIA_DIR, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(TEST_MEDIA_DIR, ignore_errors=True)

    def test_import_pages(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 12],
                ["wagtailcore.page", 15]
            ],
            "mappings": [
                ["wagtailcore.page", 12, "22222222-2222-2222-2222-222222222222"],
                ["wagtailcore.page", 15, "55555555-5555-5555-5555-555555555555"]
            ],
            "objects": [
                {
                    "model": "tests.simplepage",
                    "pk": 15,
                    "parent_id": 12,
                    "fields": {
                        "title": "Imported child page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "imported-child-page",
                        "intro": "This page is imported from the source site"
                    }
                },
                {
                    "model": "tests.simplepage",
                    "pk": 12,
                    "parent_id": 1,
                    "fields": {
                        "title": "Home",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "home",
                        "intro": "This is the updated homepage"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(12, None)
        importer.add_json(data)
        importer.run()

        updated_page = SimplePage.objects.get(url_path='/home/')
        self.assertEqual(updated_page.intro, "This is the updated homepage")

        created_page = SimplePage.objects.get(url_path='/home/imported-child-page/')
        self.assertEqual(created_page.intro, "This page is imported from the source site")

    def test_import_pages_with_fk(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 12],
                ["wagtailcore.page", 15],
                ["wagtailcore.page", 16]
            ],
            "mappings": [
                ["wagtailcore.page", 12, "22222222-2222-2222-2222-222222222222"],
                ["wagtailcore.page", 15, "00017017-5555-5555-5555-555555555555"],
                ["wagtailcore.page", 16, "00e99e99-6666-6666-6666-666666666666"],
                ["tests.advert", 11, "adadadad-1111-1111-1111-111111111111"],
                ["tests.advert", 8, "adadadad-8888-8888-8888-888888888888"],
                ["tests.author", 100, "b00cb00c-1111-1111-1111-111111111111"]
            ],
            "objects": [
                {
                    "model": "tests.simplepage",
                    "pk": 12,
                    "parent_id": 1,
                    "fields": {
                        "title": "Home",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "home",
                        "intro": "This is the updated homepage"
                    }
                },
                {
                    "model": "tests.sponsoredpage",
                    "pk": 15,
                    "parent_id": 12,
                    "fields": {
                        "title": "Oil is still great",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "oil-is-still-great",
                        "advert": 11,
                        "intro": "yay fossil fuels and climate change",
                        "author": 100,
                        "categories": []
                    }
                },
                {
                    "model": "tests.advert",
                    "pk": 11,
                    "fields": {
                        "slogan": "put a leopard in your tank"
                    }
                },
                {
                    "model": "tests.sponsoredpage",
                    "pk": 16,
                    "parent_id": 12,
                    "fields": {
                        "title": "Eggs are great too",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "eggs-are-great-too",
                        "advert": 8,
                        "intro": "you can make cakes with them",
                        "categories": []
                    }
                },
                {
                    "model": "tests.advert",
                    "pk": 8,
                    "fields": {
                        "slogan": "go to work on an egg"
                    }
                },
                {
                    "model": "tests.author",
                    "pk": 100,
                    "fields": {
                        "name": "Jack Kerouac",
                        "bio": "Jack Kerouac's car has been fixed now."
                    }
                }
            ]
        }"""

        importer = ImportPlanner(12, None)
        importer.add_json(data)
        importer.run()

        updated_page = SponsoredPage.objects.get(url_path='/home/oil-is-still-great/')
        self.assertEqual(updated_page.intro, "yay fossil fuels and climate change")
        # advert is listed in WAGTAILTRANSFER_UPDATE_RELATED_MODELS, so changes to the advert should have been pulled in too
        self.assertEqual(updated_page.advert.slogan, "put a leopard in your tank")
        # author is not listed in WAGTAILTRANSFER_UPDATE_RELATED_MODELS, so should be left unchanged
        self.assertEqual(updated_page.author.bio, "Jack Kerouac's car has broken down.")

        created_page = SponsoredPage.objects.get(url_path='/home/eggs-are-great-too/')
        self.assertEqual(created_page.intro, "you can make cakes with them")
        self.assertEqual(created_page.advert.slogan, "go to work on an egg")

    def test_import_pages_with_orphaned_uid(self):
        # the author UID listed here exists in the destination's IDMapping table, but
        # the Author record is missing; this would correspond to an author that was previously
        # imported and then deleted.
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 15]
            ],
            "mappings": [
                ["wagtailcore.page", 15, "00017017-5555-5555-5555-555555555555"],
                ["tests.advert", 11, "adadadad-1111-1111-1111-111111111111"],
                ["tests.author", 100, "b00cb00c-0000-0000-0000-00000de1e7ed"]
            ],
            "objects": [
                {
                    "model": "tests.sponsoredpage",
                    "pk": 15,
                    "parent_id": 1,
                    "fields": {
                        "title": "Oil is still great",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "oil-is-still-great",
                        "advert": 11,
                        "intro": "yay fossil fuels and climate change",
                        "author": 100,
                        "categories": []
                    }
                },
                {
                    "model": "tests.advert",
                    "pk": 11,
                    "fields": {
                        "slogan": "put a leopard in your tank"
                    }
                },
                {
                    "model": "tests.author",
                    "pk": 100,
                    "fields": {
                        "name": "Edgar Allen Poe",
                        "bio": "Edgar Allen Poe has come back from the dead"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(15, None)
        importer.add_json(data)
        importer.run()

        updated_page = SponsoredPage.objects.get(url_path='/home/oil-is-still-great/')
        # author should be recreated
        self.assertEqual(updated_page.author.name, "Edgar Allen Poe")
        self.assertEqual(updated_page.author.bio, "Edgar Allen Poe has come back from the dead")
        # make sure it has't just overwritten the old author...
        self.assertTrue(Author.objects.filter(name="Jack Kerouac").exists())

        # there should now be an IDMapping record for the previously orphaned UID, pointing to the
        # newly created author
        self.assertEqual(
            IDMapping.objects.get(uid="b00cb00c-0000-0000-0000-00000de1e7ed").content_object,
            updated_page.author
        )

    def test_import_page_with_child_models(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 100]
            ],
            "mappings": [
                ["wagtailcore.page", 100, "10000000-1000-1000-1000-100000000000"],
                ["tests.sectionedpagesection", 101, "10100000-1010-1010-1010-101000000000"],
                ["tests.sectionedpagesection", 102, "10200000-1020-1020-1020-102000000000"]
            ],
            "objects": [
                {
                    "model": "tests.sectionedpage",
                    "pk": 100,
                    "parent_id": 1,
                    "fields": {
                        "title": "How to boil an egg",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "how-to-boil-an-egg",
                        "intro": "This is how to boil an egg",
                        "sections": [
                            {
                                "model": "tests.sectionedpagesection",
                                "pk": 101,
                                "fields": {
                                    "sort_order": 0,
                                    "title": "Boil the outside of the egg",
                                    "body": "...",
                                    "page": 100
                                }
                            },
                            {
                                "model": "tests.sectionedpagesection",
                                "pk": 102,
                                "fields": {
                                    "sort_order": 1,
                                    "title": "Boil the rest of the egg",
                                    "body": "...",
                                    "page": 100
                                }
                            }
                        ]
                    }
                }
            ]
        }"""

        importer = ImportPlanner(100, 2)
        importer.add_json(data)
        importer.run()

        page = SectionedPage.objects.get(url_path='/home/how-to-boil-an-egg/')
        self.assertEqual(page.sections.count(), 2)
        self.assertEqual(page.sections.first().title, "Boil the outside of the egg")

        page_id = page.id
        sections = page.sections.all()
        section_1_id = sections[0].id
        section_2_id = sections[1].id

        # now try re-importing to update the existing page; among the child objects there will be
        # one deletion, one update and one creation

        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 100]
            ],
            "mappings": [
                ["wagtailcore.page", 100, "10000000-1000-1000-1000-100000000000"],
                ["tests.sectionedpagesection", 102, "10200000-1020-1020-1020-102000000000"],
                ["tests.sectionedpagesection", 103, "10300000-1030-1030-1030-103000000000"]
            ],
            "objects": [
                {
                    "model": "tests.sectionedpage",
                    "pk": 100,
                    "parent_id": 1,
                    "fields": {
                        "title": "How to boil an egg",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "how-to-boil-an-egg",
                        "intro": "This is still how to boil an egg",
                        "sections": [
                            {
                                "model": "tests.sectionedpagesection",
                                "pk": 102,
                                "fields": {
                                    "sort_order": 0,
                                    "title": "Boil the egg",
                                    "body": "...",
                                    "page": 100
                                }
                            },
                            {
                                "model": "tests.sectionedpagesection",
                                "pk": 103,
                                "fields": {
                                    "sort_order": 1,
                                    "title": "Eat the egg",
                                    "body": "...",
                                    "page": 100
                                }
                            }
                        ]
                    }
                }
            ]
        }"""

        importer = ImportPlanner(100, 2)
        importer.add_json(data)
        importer.run()

        new_page = SectionedPage.objects.get(id=page_id)
        self.assertEqual(new_page.intro, "This is still how to boil an egg")
        self.assertEqual(new_page.sections.count(), 2)
        new_sections = new_page.sections.all()
        self.assertEqual(new_sections[0].id, section_2_id)
        self.assertEqual(new_sections[0].title, "Boil the egg")

        self.assertNotEqual(new_sections[1].id, section_1_id)
        self.assertEqual(new_sections[1].title, "Eat the egg")

    def test_import_page_with_rich_text_link(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 15]
            ],
            "mappings": [
                ["wagtailcore.page", 12, "11111111-1111-1111-1111-111111111111"],
                ["wagtailcore.page", 15, "01010101-0005-8765-7889-987889889898"]
            ],
            "objects": [
                {
                    "model": "tests.pagewithrichtext",
                    "pk": 15,
                    "parent_id": 12,
                    "fields": {
                        "title": "Imported page with rich text",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "imported-rich-text-page",
                        "body": "<p>But I have a <a id=\\"12\\" linktype=\\"page\\">link</a></p>"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        page = PageWithRichText.objects.get(slug="imported-rich-text-page")

        # tests that a page link id is changed successfully when imported
        self.assertEqual(page.body, '<p>But I have a <a id="1" linktype="page">link</a></p>')

        # TODO: this should include an embed type as well once document/image import is added

    def test_do_not_import_pages_outside_of_selected_root(self):
        # Source page 13 is a page we don't have at the destination, but it's not in ids_for_import
        # (i.e. it's outside of the selected import root), so we shouldn't import it, and should
        # leave references in rich text unchanged
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 15]
            ],
            "mappings": [
                ["wagtailcore.page", 12, "11111111-1111-1111-1111-111111111111"],
                ["wagtailcore.page", 13, "13131313-1313-1313-1313-131313131313"],
                ["wagtailcore.page", 15, "01010101-0005-8765-7889-987889889898"]
            ],
            "objects": [
                {
                    "model": "tests.pagewithrichtext",
                    "pk": 15,
                    "parent_id": 12,
                    "fields": {
                        "title": "Imported page with rich text",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "imported-rich-text-page",
                        "body": "<p>But I have a <a id=\\"13\\" linktype=\\"page\\">link</a></p>"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        page = PageWithRichText.objects.get(slug="imported-rich-text-page")

        # tests that the page link id is unchanged
        self.assertEqual(page.body, '<p>But I have a <a id="13" linktype="page">link</a></p>')

    def test_import_page_with_streamfield_page_links(self):
        data = """{
                "ids_for_import": [
                    ["wagtailcore.page", 6]
                ],
                "mappings": [
                    ["wagtailcore.page", 6, "0c7a9390-16cb-11ea-8000-0800278dc04d"],
                    ["wagtailcore.page", 300, "33333333-3333-3333-3333-333333333333"],
                    ["wagtailcore.page", 200, "22222222-2222-2222-2222-222222222222"],
                    ["wagtailcore.page", 500, "00017017-5555-5555-5555-555555555555"],
                    ["wagtailcore.page", 100, "11111111-1111-1111-1111-111111111111"]
                ],
                "objects": [
                    {
                        "model": "tests.pagewithstreamfield",
                        "pk": 6,
                        "fields": {
                            "title": "I have a streamfield",
                            "slug": "i-have-a-streamfield",
                            "live": true,
                            "seo_title": "",
                            "show_in_menus": false,
                            "search_description": "",
                            "body": "[{\\"type\\": \\"link_block\\", \\"value\\": {\\"page\\": 100, \\"text\\": \\"Test\\"}, \\"id\\": \\"fc3b0d3d-d316-4271-9e31-84919558188a\\"}, {\\"type\\": \\"page\\", \\"value\\": 200, \\"id\\": \\"c6d07d3a-72d4-445e-8fa5-b34107291176\\"}, {\\"type\\": \\"stream\\", \\"value\\": [{\\"type\\": \\"page\\", \\"value\\": 300, \\"id\\": \\"8c0d7de7-4f77-4477-be67-7d990d0bfb82\\"}], \\"id\\": \\"21ffe52a-c0fc-4ecc-92f1-17b356c9cc94\\"}, {\\"type\\": \\"list_of_pages\\", \\"value\\": [500], \\"id\\": \\"17b972cb-a952-4940-87e2-e4eb00703997\\"}]"},
                            "parent_id": 300
                        }
                    ]
                }"""
        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        page = PageWithStreamField.objects.get(slug="i-have-a-streamfield")

        imported_streamfield = page.body.stream_block.get_prep_value(page.body)

        # Check that PageChooserBlock ids are converted correctly to those on the destination site
        self.assertEqual(imported_streamfield, [{'type': 'link_block', 'value': {'page': 1, 'text': 'Test'}, 'id': 'fc3b0d3d-d316-4271-9e31-84919558188a'}, {'type': 'page', 'value': 2, 'id': 'c6d07d3a-72d4-445e-8fa5-b34107291176'}, {'type': 'stream', 'value': [{'type': 'page', 'value': 3, 'id': '8c0d7de7-4f77-4477-be67-7d990d0bfb82'}], 'id': '21ffe52a-c0fc-4ecc-92f1-17b356c9cc94'}, {'type': 'list_of_pages', 'value': [5], 'id': '17b972cb-a952-4940-87e2-e4eb00703997'}])

    def test_import_page_with_streamfield_rich_text_block(self):
        # Check that ids in RichTextBlock within a StreamField are converted properly

        data = """{"ids_for_import": [["wagtailcore.page", 6]], "mappings": [["wagtailcore.page", 6, "a231303a-1754-11ea-8000-0800278dc04d"], ["wagtailcore.page", 100, "11111111-1111-1111-1111-111111111111"]], "objects": [{"model": "tests.pagewithstreamfield", "pk": 6, "fields": {"title": "My streamfield rich text block has a link", "slug": "my-streamfield-rich-text-block-has-a-link", "live": true, "seo_title": "", "show_in_menus": false, "search_description": "", "body": "[{\\"type\\": \\"rich_text\\", \\"value\\": \\"<p>I link to a <a id=\\\\\\"100\\\\\\" linktype=\\\\\\"page\\\\\\">page</a>.</p>\\", \\"id\\": \\"7d4ee3d4-9213-4319-b984-45be4ded8853\\"}]"}, "parent_id": 100}]}"""
        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        page = PageWithStreamField.objects.get(slug="my-streamfield-rich-text-block-has-a-link")

        imported_streamfield = page.body.stream_block.get_prep_value(page.body)

        self.assertEqual(imported_streamfield, [{'type': 'rich_text', 'value': '<p>I link to a <a id="1" linktype="page">page</a>.</p>', 'id': '7d4ee3d4-9213-4319-b984-45be4ded8853'}])

    @mock.patch('requests.get')
    def test_import_image_with_file(self, get):
        get.return_value.status_code = 200
        get.return_value.content = b'my test image file contents'

        IDMapping.objects.get_or_create(
            uid="f91cb31c-1751-11ea-8000-0800278dc04d",
            defaults={
                'content_type': ContentType.objects.get_for_model(Collection),
                'local_id':  Collection.objects.get().id,
            }
        )

        data = """{
            "ids_for_import": [
                ["wagtailimages.image", 53]
            ],
            "mappings": [
                ["wagtailcore.collection", 3, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailimages.image", 53, "f91debc6-1751-11ea-8001-0800278dc04d"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 3,
                    "fields": {
                        "name": "Root"
                    },
                    "parent_id": null
                },
                {
                    "model": "wagtailimages.image",
                    "pk": 53,
                    "fields": {
                        "collection": 3,
                        "title": "Lightnin' Hopkins",
                        "file": {
                            "download_url": "https://wagtail.io/media/original_images/lightnin_hopkins.jpg",
                            "size": 18521,
                            "hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada"
                        },
                        "width": 150,
                        "height": 162,
                        "created_at": "2019-04-01T07:31:21.251Z",
                        "uploaded_by_user": null,
                        "focal_point_x": null,
                        "focal_point_y": null,
                        "focal_point_width": null,
                        "focal_point_height": null,
                        "file_size": 18521,
                        "file_hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada",
                        "tags": "[]",
                        "tagged_items": "[]"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        # Check the image was imported
        get.assert_called()
        image = Image.objects.get()
        self.assertEqual(image.title, "Lightnin' Hopkins")
        self.assertEqual(image.file.read(), b'my test image file contents')

        # TODO: We should verify these
        self.assertEqual(image.file_size, 18521)
        self.assertEqual(image.file_hash, "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada")

    @mock.patch('requests.get')
    def test_import_image_with_file_without_root_collection_mapping(self, get):
        get.return_value.status_code = 200
        get.return_value.content = b'my test image file contents'

        data = """{
            "ids_for_import": [
                ["wagtailimages.image", 53]
            ],
            "mappings": [
                ["wagtailcore.collection", 3, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailimages.image", 53, "f91debc6-1751-11ea-8001-0800278dc04d"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 3,
                    "fields": {
                        "name": "the other root"
                    },
                    "parent_id": null
                },
                {
                    "model": "wagtailimages.image",
                    "pk": 53,
                    "fields": {
                        "collection": 3,
                        "title": "Lightnin' Hopkins",
                        "file": {
                            "download_url": "https://wagtail.io/media/original_images/lightnin_hopkins.jpg",
                            "size": 18521,
                            "hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada"
                        },
                        "width": 150,
                        "height": 162,
                        "created_at": "2019-04-01T07:31:21.251Z",
                        "uploaded_by_user": null,
                        "focal_point_x": null,
                        "focal_point_y": null,
                        "focal_point_width": null,
                        "focal_point_height": null,
                        "file_size": 18521,
                        "file_hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada",
                        "tags": "[]",
                        "tagged_items": "[]"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        # Check the image was imported
        get.assert_called()
        image = Image.objects.get()
        self.assertEqual(image.title, "Lightnin' Hopkins")
        self.assertEqual(image.file.read(), b'my test image file contents')

        # It should be in the existing root collection (no new collection should be created)
        self.assertEqual(image.collection.name, "Root")
        self.assertEqual(Collection.objects.count(), 1)

        # TODO: We should verify these
        self.assertEqual(image.file_size, 18521)
        self.assertEqual(image.file_hash, "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada")

    @mock.patch('requests.get')
    def test_existing_image_is_not_refetched(self, get):
        """
        If an incoming object has a FileField that reports the same size/hash as the existing
        file, we should not refetch the file
        """

        get.return_value.status_code = 200
        get.return_value.content = b'my test image file contents'

        with open(os.path.join(FIXTURES_DIR, 'wagtail.jpg'), 'rb') as f:
            image = Image.objects.create(
                title="Wagtail",
                file=ImageFile(f, name='wagtail.jpg')
            )

        IDMapping.objects.get_or_create(
            uid="f91debc6-1751-11ea-8001-0800278dc04d",
            defaults={
                'content_type': ContentType.objects.get_for_model(Image),
                'local_id': image.id,
            }
        )

        data = """{
            "ids_for_import": [
                ["wagtailimages.image", 53]
            ],
            "mappings": [
                ["wagtailcore.collection", 3, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailimages.image", 53, "f91debc6-1751-11ea-8001-0800278dc04d"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 3,
                    "fields": {
                        "name": "root"
                    },
                    "parent_id": null
                },
                {
                    "model": "wagtailimages.image",
                    "pk": 53,
                    "fields": {
                        "collection": 3,
                        "title": "A lovely wagtail",
                        "file": {
                            "download_url": "https://wagtail.io/media/original_images/wagtail.jpg",
                            "size": 1160,
                            "hash": "45c5db99aea04378498883b008ee07528f5ae416"
                        },
                        "width": 32,
                        "height": 40,
                        "created_at": "2019-04-01T07:31:21.251Z",
                        "uploaded_by_user": null,
                        "focal_point_x": null,
                        "focal_point_y": null,
                        "focal_point_width": null,
                        "focal_point_height": null,
                        "file_size": 1160,
                        "file_hash": "45c5db99aea04378498883b008ee07528f5ae416",
                        "tags": "[]",
                        "tagged_items": "[]"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        get.assert_not_called()
        image = Image.objects.get()
        # Metadata was updated...
        self.assertEqual(image.title, "A lovely wagtail")
        # but file is left alone (i.e. it has not been replaced with 'my test image file contents')
        self.assertEqual(image.file.size, 1160)

    @mock.patch('requests.get')
    def test_replace_image(self, get):
        """
        If an incoming object has a FileField that reports a different size/hash to the existing
        file, we should fetch it and update the field
        """

        get.return_value.status_code = 200
        get.return_value.content = b'my test image file contents'

        with open(os.path.join(FIXTURES_DIR, 'wagtail.jpg'), 'rb') as f:
            image = Image.objects.create(
                title="Wagtail",
                file=ImageFile(f, name='wagtail.jpg')
            )

        IDMapping.objects.get_or_create(
            uid="f91debc6-1751-11ea-8001-0800278dc04d",
            defaults={
                'content_type': ContentType.objects.get_for_model(Image),
                'local_id': image.id,
            }
        )

        data = """{
            "ids_for_import": [
                ["wagtailimages.image", 53]
            ],
            "mappings": [
                ["wagtailcore.collection", 3, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailimages.image", 53, "f91debc6-1751-11ea-8001-0800278dc04d"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 3,
                    "fields": {
                        "name": "root"
                    },
                    "parent_id": null
                },
                {
                    "model": "wagtailimages.image",
                    "pk": 53,
                    "fields": {
                        "collection": 3,
                        "title": "A lovely wagtail",
                        "file": {
                            "download_url": "https://wagtail.io/media/original_images/wagtail.jpg",
                            "size": 27,
                            "hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada"
                        },
                        "width": 32,
                        "height": 40,
                        "created_at": "2019-04-01T07:31:21.251Z",
                        "uploaded_by_user": null,
                        "focal_point_x": null,
                        "focal_point_y": null,
                        "focal_point_width": null,
                        "focal_point_height": null,
                        "file_size": 27,
                        "file_hash": "e4eab12cc50b6b9c619c9ddd20b61d8e6a961ada",
                        "tags": "[]",
                        "tagged_items": "[]"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        get.assert_called()
        image = Image.objects.get()
        self.assertEqual(image.title, "A lovely wagtail")
        self.assertEqual(image.file.read(), b'my test image file contents')

    def test_import_collection(self):
        root_collection = Collection.objects.get()

        IDMapping.objects.get_or_create(
            uid="f91cb31c-1751-11ea-8000-0800278dc04d",
            defaults={
                'content_type': ContentType.objects.get_for_model(Collection),
                'local_id':  root_collection.id,
            }
        )

        data = """{
            "ids_for_import": [
                ["wagtailcore.collection", 4]
            ],
            "mappings": [
                ["wagtailcore.collection", """ + str(root_collection.id) + """, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailcore.collection", 4, "8a1d3afd-3fa2-4309-9dc7-6d31902174ca"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 4,
                    "fields": {
                        "name": "New collection"
                    },
                    "parent_id": """ + str(root_collection.id) + """
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        # Check the new collection was imported
        collection = Collection.objects.get(name="New collection")
        self.assertEqual(collection.get_parent(), root_collection)

    def test_import_collection_without_root_collection_mapping(self):
        root_collection = Collection.objects.get()
        data = """{
            "ids_for_import": [
                ["wagtailcore.collection", 4]
            ],
            "mappings": [
                ["wagtailcore.collection", 1, "f91cb31c-1751-11ea-8000-0800278dc04d"],
                ["wagtailcore.collection", 4, "8a1d3afd-3fa2-4309-9dc7-6d31902174ca"]
            ],
            "objects": [
                {
                    "model": "wagtailcore.collection",
                    "pk": 4,
                    "fields": {
                        "name": "New collection"
                    },
                    "parent_id": 1
                },
                {
                    "model": "wagtailcore.collection",
                    "pk": 1,
                    "fields": {
                        "name": "source site root"
                    },
                    "parent_id": null
                }
            ]
        }"""

        importer = ImportPlanner(1, None)
        importer.add_json(data)
        importer.run()

        # Check the new collection was imported into the existing root collection
        collection = Collection.objects.get(name="New collection")
        self.assertEqual(collection.get_parent(), root_collection)
        # Only the root and the imported collection should exist
        self.assertEqual(Collection.objects.count(), 2)

    def test_import_page_with_parental_many_to_many(self):
        # Test that a page with a ParentalManyToManyField has its ids translated to the destination site's appropriately
        data = """{
            "ids_for_import": [["wagtailcore.page", 6]],
            "mappings": [
                ["tests.advert", 200, "adadadad-2222-2222-2222-222222222222"],
                ["wagtailcore.page", 6, "a98b0848-1a96-11ea-8001-0800278dc04d"],
                ["tests.advert", 300, "adadadad-3333-3333-3333-333333333333"]
            ],
            "objects": [
                {"model": "tests.pagewithparentalmanytomany", "pk": 6, "fields": {"title": "This page has lots of ads!", "slug": "this-page-has-lots-of-ads", "live": true, "seo_title": "", "show_in_menus": false, "search_description": "", "ads": [200, 300]}, "parent_id": 1},
                {
                    "model": "tests.advert",
                    "pk": 200,
                    "fields": {"slogan": "Buy a thing you definitely need!"}
                },
                {
                    "model": "tests.advert",
                    "pk": 300,
                    "fields": {"slogan": "Buy a half-scale authentically hydrogen-filled replica of the Hindenburg!"}
                }
            ]}
        """

        importer = ImportPlanner(6, 3)
        importer.add_json(data)
        importer.run()

        page = PageWithParentalManyToMany.objects.get(slug="this-page-has-lots-of-ads")

        advert_2 = Advert.objects.get(id=2)
        advert_3 = Advert.objects.get(id=3)

        self.assertEqual(set(page.ads.all()), {advert_2, advert_3})

        # advert is listed in WAGTAILTRANSFER_UPDATE_RELATED_MODELS, so changes to the advert should have been pulled in too
        self.assertEqual(advert_3.slogan, "Buy a half-scale authentically hydrogen-filled replica of the Hindenburg!")

    def test_import_object_with_many_to_many(self):
        # Test that an imported object with a ManyToManyField has its ids converted to the destination site's
        data = """{
            "ids_for_import": [["tests.modelwithmanytomany", 1]],
            "mappings": [
                ["tests.advert", 200, "adadadad-2222-2222-2222-222222222222"],
                ["tests.advert", 300, "adadadad-3333-3333-3333-333333333333"],
                ["tests.modelwithmanytomany", 1, "6a5e5e52-1aa0-11ea-8002-0800278dc04d"]
            ],
            "objects": [
                {"model": "tests.modelwithmanytomany", "pk": 1, "fields": {"ads": [200, 300]}},
                {
                    "model": "tests.advert",
                    "pk": 200,
                    "fields": {"slogan": "Buy a thing you definitely need!"}
                },
                {
                    "model": "tests.advert",
                    "pk": 300,
                    "fields": {"slogan": "Buy a half-scale authentically hydrogen-filled replica of the Hindenburg!"}
                }
            ]}"""

        importer = ImportPlanner(6, 3)
        importer.add_json(data)
        importer.run()

        ad_holder = ModelWithManyToMany.objects.get(id=1)
        advert_2 = Advert.objects.get(id=2)
        advert_3 = Advert.objects.get(id=3)
        self.assertEqual(set(ad_holder.ads.all()), {advert_2, advert_3})

        # advert is listed in WAGTAILTRANSFER_UPDATE_RELATED_MODELS, so changes to the advert should have been pulled in too
        self.assertEqual(advert_3.slogan, "Buy a half-scale authentically hydrogen-filled replica of the Hindenburg!")

    def test_import_with_field_based_lookup(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 15]
            ],
            "mappings": [
                ["wagtailcore.page", 15, "00017017-5555-5555-5555-555555555555"],
                ["tests.advert", 11, "adadadad-1111-1111-1111-111111111111"],
                ["tests.author", 100, "b00cb00c-1111-1111-1111-111111111111"],
                ["tests.category", 101, ["Cars"]],
                ["tests.category", 102, ["Environment"]]
            ],
            "objects": [
                {
                    "model": "tests.sponsoredpage",
                    "pk": 15,
                    "parent_id": 1,
                    "fields": {
                        "title": "Oil is still great",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "oil-is-still-great",
                        "advert": 11,
                        "intro": "yay fossil fuels and climate change",
                        "author": 100,
                        "categories": [101, 102]
                    }
                },
                {
                    "model": "tests.advert",
                    "pk": 11,
                    "fields": {
                        "slogan": "put a leopard in your tank"
                    }
                },
                {
                    "model": "tests.author",
                    "pk": 100,
                    "fields": {
                        "name": "Jack Kerouac",
                        "bio": "Jack Kerouac's car has been fixed now."
                    }
                },
                {
                    "model": "tests.category",
                    "pk": 102,
                    "fields": {
                        "name": "Environment",
                        "colour": "green"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(15, None)
        importer.add_json(data)
        importer.run()

        updated_page = SponsoredPage.objects.get(url_path='/home/oil-is-still-great/')
        # The 'Cars' category should have been matched by name to the existing record
        self.assertEqual(updated_page.categories.get(name='Cars').colour, "red")
        # The 'Environment' category should have been created
        self.assertEqual(updated_page.categories.get(name='Environment').colour, "green")

    def test_skip_import_if_hard_dependency_on_non_imported_page(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 20],
                ["wagtailcore.page", 21],
                ["wagtailcore.page", 23],
                ["wagtailcore.page", 24],
                ["wagtailcore.page", 25],
                ["wagtailcore.page", 26],
                ["wagtailcore.page", 27]
            ],
            "mappings": [
                ["wagtailcore.page", 20, "20202020-2020-2020-2020-202020202020"],
                ["wagtailcore.page", 21, "21212121-2121-2121-2121-212121212121"],
                ["wagtailcore.page", 23, "23232323-2323-2323-2323-232323232323"],
                ["wagtailcore.page", 24, "24242424-2424-2424-2424-242424242424"],
                ["wagtailcore.page", 25, "25252525-2525-2525-2525-252525252525"],
                ["wagtailcore.page", 26, "26262626-2626-2626-2626-262626262626"],
                ["wagtailcore.page", 27, "27272727-2727-2727-2727-272727272727"],
                ["wagtailcore.page", 30, "00017017-5555-5555-5555-555555555555"],
                ["wagtailcore.page", 31, "31313131-3131-3131-3131-313131313131"]
            ],
            "objects": [
                {
                    "model": "tests.simplepage",
                    "pk": 20,
                    "parent_id": 12,
                    "fields": {
                        "title": "hard dependency test",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "hard-dependency-test",
                        "intro": "Testing hard dependencies on pages outside the imported root"
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 21,
                    "parent_id": 20,
                    "fields": {
                        "title": "redirect to oil page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "redirect-to-oil-page",
                        "redirect_to": 30
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 23,
                    "parent_id": 20,
                    "fields": {
                        "title": "redirect to unimported page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "redirect-to-unimported-page",
                        "redirect_to": 31
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 24,
                    "parent_id": 20,
                    "fields": {
                        "title": "redirect to redirect to oil page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "redirect-to-redirect-to-oil-page",
                        "redirect_to": 21
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 25,
                    "parent_id": 20,
                    "fields": {
                        "title": "redirect to redirect to unimported page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "redirect-to-redirect-to-unimported-page",
                        "redirect_to": 23
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 26,
                    "parent_id": 20,
                    "fields": {
                        "title": "pork redirecting to lamb",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "pork-redirecting-to-lamb",
                        "redirect_to": 27
                    }
                },
                {
                    "model": "tests.redirectpage",
                    "pk": 27,
                    "parent_id": 20,
                    "fields": {
                        "title": "lamb redirecting to pork",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "lamb-redirecting-to-pork",
                        "redirect_to": 26
                    }
                }
            ]
        }"""

        importer = ImportPlanner(20, 2)
        importer.add_json(data)
        importer.run()

        # A non-nullable FK to an existing page outside the imported root is fine
        redirect_to_oil_page = RedirectPage.objects.get(slug='redirect-to-oil-page')
        self.assertEqual(redirect_to_oil_page.redirect_to.slug, 'oil-is-great')

        # A non-nullable FK to a non-existing page outside the imported root will prevent import
        self.assertFalse(RedirectPage.objects.filter(slug='redirect-to-unimported-page').exists())

        # We can also handle FKs to pages being created in the import
        redirect_to_redirect_to_oil_page = RedirectPage.objects.get(slug='redirect-to-redirect-to-oil-page')
        self.assertEqual(redirect_to_redirect_to_oil_page.redirect_to.slug, 'redirect-to-oil-page')

        # Failure to create a page will also propagate to pages with a hard dependency on it
        self.assertFalse(RedirectPage.objects.filter(slug='redirect-to-redirect-to-unimported-page').exists())

        # Circular references will be caught and pages not created
        self.assertFalse(RedirectPage.objects.filter(slug='pork-redirecting-to-lamb').exists())
        self.assertFalse(RedirectPage.objects.filter(slug='lamb-redirecting-to-pork').exists())

    def test_circular_references_in_rich_text(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 20],
                ["wagtailcore.page", 21],
                ["wagtailcore.page", 23]
            ],
            "mappings": [
                ["wagtailcore.page", 20, "20202020-2020-2020-2020-202020202020"],
                ["wagtailcore.page", 21, "21212121-2121-2121-2121-212121212121"],
                ["wagtailcore.page", 23, "23232323-2323-2323-2323-232323232323"]
            ],
            "objects": [
                {
                    "model": "tests.simplepage",
                    "pk": 20,
                    "parent_id": 12,
                    "fields": {
                        "title": "circular dependency test",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "circular-dependency-test",
                        "intro": "Testing circular dependencies in rich text links"
                    }
                },
                {
                    "model": "tests.pagewithrichtext",
                    "pk": 21,
                    "parent_id": 20,
                    "fields": {
                        "title": "Bill's page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "bill",
                        "body": "<p>Have you met my friend <a id=\\"23\\" linktype=\\"page\\">Ben</a>?</p>"
                    }
                },
                {
                    "model": "tests.pagewithrichtext",
                    "pk": 23,
                    "parent_id": 20,
                    "fields": {
                        "title": "Ben's page",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "ben",
                        "body": "<p>Have you met my friend <a id=\\"21\\" linktype=\\"page\\">Bill</a>?</p>"
                    }
                }
            ]
        }"""

        importer = ImportPlanner(20, 2)
        importer.add_json(data)
        importer.run()

        # Both pages should have been created
        bill_page = PageWithRichText.objects.get(slug='bill')
        ben_page = PageWithRichText.objects.get(slug='ben')

        # At least one of them (i.e. the second one to be created) should have a valid link to the other
        self.assertTrue(
            bill_page.body == """<p>Have you met my friend <a id="%d" linktype="page">Ben</a>?</p>""" % ben_page.id
            or
            ben_page.body == """<p>Have you met my friend <a id="%d" linktype="page">Bill</a>?</p>""" % bill_page.id
        )

    def test_omitting_references_in_m2m_relations(self):
        data = """{
            "ids_for_import": [
                ["wagtailcore.page", 20],
                ["wagtailcore.page", 21],
                ["wagtailcore.page", 23]
            ],
            "mappings": [
                ["wagtailcore.page", 20, "20202020-2020-2020-2020-202020202020"],
                ["wagtailcore.page", 21, "21212121-2121-2121-2121-212121212121"],
                ["wagtailcore.page", 23, "23232323-2323-2323-2323-232323232323"],
                ["wagtailcore.page", 30, "00017017-5555-5555-5555-555555555555"],
                ["wagtailcore.page", 31, "31313131-3131-3131-3131-313131313131"]
            ],
            "objects": [
                {
                    "model": "tests.simplepage",
                    "pk": 20,
                    "parent_id": 12,
                    "fields": {
                        "title": "m2m reference test",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "m2m-reference-test",
                        "intro": "Testing references and dependencies on m2m relations"
                    }
                },
                {
                    "model": "tests.simplepage",
                    "pk": 21,
                    "parent_id": 20,
                    "fields": {
                        "title": "vinegar",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "vinegar",
                        "intro": "it's pickling time"
                    }
                },
                {
                    "model": "tests.pagewithrelatedpages",
                    "pk": 23,
                    "parent_id": 20,
                    "fields": {
                        "title": "salad dressing",
                        "show_in_menus": false,
                        "live": true,
                        "slug": "salad-dressing",
                        "related_pages": [21,30,31]
                    }
                }
            ]
        }"""

        importer = ImportPlanner(20, 2)
        importer.add_json(data)
        importer.run()

        salad_dressing_page = PageWithRelatedPages.objects.get(slug='salad-dressing')
        oil_page = Page.objects.get(slug='oil-is-great')
        vinegar_page = Page.objects.get(slug='vinegar')

        # salad_dressing_page's related_pages should include the oil (id=30) and vinegar (id=21)
        # pages, but not the missing and not-to-be-imported page id=31
        self.assertEqual(set(salad_dressing_page.related_pages.all()), set([oil_page, vinegar_page]))
